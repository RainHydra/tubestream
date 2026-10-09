# 🌐 Deployment Guide for TubeStream Pro

This guide walks you through deploying the **YouTube Video & Playlist Downloader** web application to production across various platforms.

---

## 📋 Table of Contents
1. [Prerequisites & Git Setup](#1-git-setup-recommended-first-step)
2. [Option 1: Deploy on Render.com (Recommended Free/Easy)](#option-1-deploy-on-rendercom-recommended-free-tier)
3. [Option 2: Deploy on Railway.app](#option-2-deploy-on-railwayapp)
4. [Option 3: Deploy with Docker / Docker Compose (Any VPS)](#option-3-deploy-with-docker--docker-compose-any-vps)
5. [Option 4: Deploy on Ubuntu VPS (Native Systemd + Nginx + SSL)](#option-4-deploy-on-ubuntu-vps-native-systemd--nginx--ssl)
6. [Option 5: Deploy on Hugging Face Spaces (Free Docker Hosting)](#option-5-deploy-on-hugging-face-spaces-free-docker-hosting)

---

## 1. Git Setup (Recommended First Step)

Most cloud providers connect directly to your GitHub/GitLab repository for automated builds and continuous deployment.

Run the following commands in the project folder:

```bash
# Initialize git repository
git init

# Add all project files
git add .

# Create initial commit
git commit -m "Initial commit: Ready for deployment"

# Create a new repo on GitHub (e.g. yt-downloader-app), then link it:
git remote add origin https://github.com/YOUR_USERNAME/yt-downloader-app.git
git branch -M main
git push -u origin main
```

---

## Option 1: Deploy on Render.com (Recommended Free Tier)

Render provides free hosting with automatic Docker builds and SSL certificates.

### Step-by-Step:
1. Go to [Render.com](https://render.com) and sign in with GitHub.
2. Click **New +** in the top navigation bar and select **Web Service**.
3. Select **Build and deploy from a Git repository** and connect your `yt-downloader-app` repository.
4. Fill in the settings:
   - **Name**: `yt-downloader-app` (or your choice)
   - **Region**: Choose closest to your audience (e.g., Oregon, Frankfurt, Singapore)
   - **Language / Runtime**: Select **Docker** (The included `Dockerfile` will automatically install FFmpeg and Python dependencies)
   - **Instance Type**: **Free**
5. Click **Create Web Service**.
6. Render will automatically build the Docker container and provide you with a live URL (e.g. `https://yt-downloader-app.onrender.com`).

---

## Option 2: Deploy on Railway.app

Railway offers fast one-click deployments from GitHub with generous trial/pay-as-you-go credits.

### Step-by-Step:
1. Go to [Railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** > **Deploy from GitHub repo**.
3. Select your `yt-downloader-app` repository.
4. Railway automatically detects the `Dockerfile` and builds it.
5. In your project settings on Railway:
   - Go to **Settings** > **Networking** > **Generate Domain**.
6. Your app is live with a public HTTPS URL.

---

## Option 3: Deploy with Docker / Docker Compose (Any VPS)

If you have a Linux VPS (DigitalOcean, AWS EC2, Linode, Hetzner, Oracle Cloud, etc.):

### 1. Install Docker & Docker Compose on your server:
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### 2. Clone and start the application:
```bash
git clone https://github.com/YOUR_USERNAME/yt-downloader-app.git
cd yt-downloader-app

# Build and start in detached background mode
docker compose up -d --build
```

### 3. Check container status:
```bash
docker ps
docker logs -f yt-downloader-app
```

Your app will be running at `http://YOUR_SERVER_IP:8000`.

---

## Option 4: Deploy on Ubuntu VPS (Native Systemd + Nginx + SSL)

If you prefer running natively on Ubuntu/Debian with Nginx reverse proxy and Let's Encrypt SSL:

### 1. Install system dependencies & FFmpeg:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg nginx certbot python3-certbot-nginx
```

### 2. Clone repo and create virtual environment:
```bash
sudo mkdir -p /var/www/yt-downloader
sudo chown $USER:$USER /var/www/yt-downloader
git clone https://github.com/YOUR_USERNAME/yt-downloader-app.git /var/www/yt-downloader
cd /var/www/yt-downloader

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create Systemd Service:
Create `/etc/systemd/system/ytdl.service`:
```ini
[Unit]
Description=TubeStream Pro FastAPI Downloader
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/yt-downloader
Environment="PATH=/var/www/yt-downloader/venv/bin"
Environment="PORT=8000"
Environment="HOST=127.0.0.1"
ExecStart=/var/www/yt-downloader/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo chown -R www-data:www-data /var/www/yt-downloader
sudo systemctl daemon-reload
sudo systemctl enable --now ytdl
```

### 4. Configure Nginx Reverse Proxy:
Create `/etc/nginx/sites-available/ytdl`:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Crucial for SSE progress streams
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

Enable the site and obtain SSL:
```bash
sudo ln -s /etc/nginx/sites-available/ytdl /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## Option 5: Deploy on Hugging Face Spaces (Free Docker Hosting)

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) and click **Create new Space**.
2. Set SDK to **Docker** (Blank template).
3. Clone the space repo locally or upload all project files directly.
4. Hugging Face will build the Docker container and expose port 7860/8000 with a free public URL.

---

## ⚙️ Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Port on which the web server listens |
| `HOST` | `0.0.0.0` | Network binding host address |
| `RELOAD` | `false` | Enable/disable auto-reloading (set `true` for development only) |

---

## 💡 YouTube Download Reliability Tips in the Cloud

- Datacenter IPs: Some cloud providers (e.g. AWS or GCP IP ranges) might occasionally trigger YouTube bot checks for certain high-volume requests. Using **Docker on Render, Railway, Koyeb, or a residential/VPS IP** provides high reliability.
- **Auto-Cleanup**: The built-in auto-cleanup worker ensures the server's disk space is recycled continuously after 20 minutes of inactivity or immediately following downloads.
