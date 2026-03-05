import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

BASE_URL = "https://api.opensubtitles.com/api/v1"

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French",
    "pt": "Portuguese", "pt-br": "Portuguese (Brazil)", "de": "German",
    "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "zh-hans": "Chinese (Simplified)", "zh-hant": "Chinese (Traditional)",
    "ru": "Russian", "ar": "Arabic", "nl": "Dutch", "pl": "Polish",
    "sv": "Swedish", "da": "Danish", "fi": "Finnish", "nb": "Norwegian",
    "tr": "Turkish", "cs": "Czech", "ro": "Romanian", "hu": "Hungarian",
    "el": "Greek", "he": "Hebrew", "uk": "Ukrainian", "id": "Indonesian",
    "vi": "Vietnamese", "th": "Thai",
}

NOISE_TAGS = [
    "720p", "1080p", "2160p", "4K", "UHD", "BluRay", "BRRip", "WEBRip", "WEB-DL",
    "HDTV", "DVDRip", "x264", "x265", "HEVC", "AVC", "H264", "H265", "AAC", "AC3",
    "DTS", "mp4", "mkv", "avi", "EXTENDED", "REMASTERED", "THEATRICAL", "DIRECTORS",
    "UNRATED", "PROPER", "REPACK",
]


def get_headers() -> dict:
    return {
        "Api-Key": os.getenv("OPENSUBTITLES_API_KEY", ""),
        "User-Agent": f"{os.getenv('OPENSUBTITLES_APP_NAME', 'SubFinder')} v{os.getenv('OPENSUBTITLES_APP_VERSION', '1.0.0')}",
        "Accept": "application/json",
    }


def clean_filename(filename: str) -> str:
    name = Path(filename).stem
    for tag in NOISE_TAGS:
        name = re.sub(rf"\b{re.escape(tag)}\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[.\-_]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def parse_api_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        return body.get("message") or body.get("error") or f"OpenSubtitles API error (HTTP {response.status_code})"
    except Exception:
        return f"OpenSubtitles API error (HTTP {response.status_code})"


class SearchRequest(BaseModel):
    filename: str
    language: str = "en"


class DownloadRequest(BaseModel):
    file_id: int
    filename: str
    language: str = "en"


@app.post("/subtitles/search")
async def search(req: SearchRequest):
    query = clean_filename(req.filename)
    if not query:
        return {"success": False, "message": "No filename provided."}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(
                f"{BASE_URL}/subtitles",
                params={"query": query, "languages": req.language, "per_page": 5},
                headers=get_headers(),
            )
    except httpx.TimeoutException:
        return {"success": False, "message": "Request timed out. Please try again."}
    except Exception as e:
        return {"success": False, "message": f"Search failed: {e}"}

    if not response.is_success:
        return {"success": False, "message": parse_api_error(response)}

    subtitles = response.json().get("data", [])

    if not subtitles:
        lang_name = LANGUAGE_NAMES.get(req.language, req.language.upper())
        return {"success": False, "message": f'No {lang_name} subtitles found for "{query}". Try a different language or check the filename.'}

    best = subtitles[0]
    attributes = best.get("attributes", {})
    file = (attributes.get("files") or [{}])[0]
    feature = attributes.get("feature_details") or {}

    return {
        "success": True,
        "file_id": file.get("file_id"),
        "movie_name": feature.get("movie_name") or feature.get("title") or query,
        "release": attributes.get("release"),
        "language": attributes.get("language"),
        "download_count": attributes.get("download_count"),
    }


@app.post("/subtitles/download")
async def download(req: DownloadRequest):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.post(
                f"{BASE_URL}/download",
                json={"file_id": req.file_id},
                headers=get_headers(),
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Download timed out. Please try again.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")

    if not response.is_success:
        raise HTTPException(status_code=response.status_code, detail=parse_api_error(response))

    data = response.json()
    download_url = data.get("link")
    remote_filename = data.get("file_name", "subtitle.srt")

    if not download_url:
        raise HTTPException(status_code=500, detail="Could not get download link from OpenSubtitles.")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            subtitle_response = await client.get(download_url)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Download timed out. Please try again.")

    if not subtitle_response.is_success:
        raise HTTPException(status_code=500, detail="Failed to download subtitle file.")

    ext = Path(remote_filename).suffix.lower() or ".srt"
    output_filename = f"{Path(req.filename).stem}{ext}"

    return Response(
        content=subtitle_response.content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{output_filename}"'},
    )


# Must be last — catches all unmatched routes and serves static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")
