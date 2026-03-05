# SubFinder

A Python/FastAPI web app that finds and downloads subtitles for any video file via the [OpenSubtitles](https://www.opensubtitles.com) API. Drop a video file onto the page, pick a language (default: English), and download the subtitle file renamed to match your video.

---

## Requirements

- Docker & Docker Compose
- An OpenSubtitles API key → https://www.opensubtitles.com/consumers (free tier available)

---

## Local development

### 1. Clone and configure

```bash
git clone <your-repo-url> subfinder
cd subfinder
cp .env.example .env
```

Edit `.env` and fill in your values:

```
OPENSUBTITLES_API_KEY=your_key_here
```

### 2. Start with Docker Compose

```bash
docker compose up --build
```

The app will be available at **http://localhost:3000**.

To run in detached mode:

```bash
docker compose up -d --build
```

---

## Deploy to a Digital Ocean Droplet

### Step 1 – Create a Droplet

- Choose **Ubuntu 22.04 LTS**
- Size: **1 GB RAM / 1 vCPU** minimum (Basic plan)
- Add your SSH key during creation

### Step 2 – Install Docker on the Droplet

```bash
ssh root@YOUR_DROPLET_IP

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt-get install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

### Step 3 – Copy the app to the server

**Option A – Git (recommended)**

```bash
# On the droplet
git clone <your-repo-url> /opt/subfinder
cd /opt/subfinder
```

**Option B – rsync from your machine**

```bash
rsync -avz --exclude='.git' \
  ./subfinder/ root@YOUR_DROPLET_IP:/opt/subfinder/
```

### Step 4 – Configure environment

```bash
cd /opt/subfinder
cp .env.example .env
nano .env   # fill in your API key
```

### Step 5 – Build and start

```bash
cd /opt/subfinder
docker compose up -d --build
```

Check logs:

```bash
docker compose logs -f web
```

The app is now running on port **3000**. Test it:

```bash
curl http://YOUR_DROPLET_IP:3000
```

### Step 6 – (Recommended) Put Nginx in front with HTTPS

Install Nginx and Certbot:

```bash
apt-get install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/subfinder`:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN.com www.YOUR_DOMAIN.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        client_max_body_size 50M;
    }
}
```

Enable and get a certificate:

```bash
ln -s /etc/nginx/sites-available/subfinder /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d YOUR_DOMAIN.com -d www.YOUR_DOMAIN.com
```

### Step 7 – Auto-start on reboot

```bash
cat > /etc/systemd/system/subfinder.service << 'EOF'
[Unit]
Description=SubFinder Docker Compose
Requires=docker.service
After=docker.service

[Service]
WorkingDirectory=/opt/subfinder
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable subfinder
systemctl start subfinder
```

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `OPENSUBTITLES_API_KEY` | **Yes** | Your OpenSubtitles REST API key |
| `OPENSUBTITLES_APP_NAME` | No | App name sent in User-Agent (default: SubFinder) |
| `OPENSUBTITLES_APP_VERSION` | No | App version in User-Agent (default: 1.0.0) |

---

## Project structure

```
subfinder/
├── main.py                  # FastAPI app: search & download endpoints
├── static/
│   └── index.html           # Frontend UI (Stimulus, Tailwind)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## How it works

1. User drops (or selects) a video file — **only the filename is read**, the file is never uploaded.
2. The filename is cleaned up (strips quality tags like `1080p`, `BluRay`, etc.) and sent to OpenSubtitles.
3. The best matching subtitle is found and its download token retrieved.
4. The subtitle is downloaded server-side and served to the browser **renamed to match the video filename** (e.g. `My.Movie.2023.mkv` → `My.Movie.2023.srt`).

---

## Notes

- OpenSubtitles free accounts have a **daily download limit** (currently 20/day). Register at https://www.opensubtitles.com to get an API key.
