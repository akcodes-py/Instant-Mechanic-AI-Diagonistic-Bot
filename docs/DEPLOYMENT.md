# Deployment

## Architecture
- **Frontend:** AWS S3 (static hosting) + CloudFront (CDN + HTTPS)
- **Backend:** AWS EC2 t2.micro (Ubuntu) + Docker Compose + Nginx
- **Backend stack:** FastAPI + Uvicorn, async SQLAlchemy + aiosqlite, tables created on startup

---

## Backend → EC2 (Ubuntu + Docker)

### 1. Launch EC2
- AMI: Ubuntu Server 24.04 LTS (free tier)
- Type: t2.micro | Security group: ports 22, 80, 443 open
- Storage: 20 GB gp3

### 2. Install Docker
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker ubuntu && newgrp docker
```

### 3. Clone & Configure
```bash
git clone https://github.com/akcodes-py/Instant-Mechanic-AI-Diagonistic-Bot.git app
cd app
sudo mkdir -p /data/media && sudo chown -R ubuntu:ubuntu /data

cat > .env << 'EOF'
DEBUG=False
DATABASE_URL=sqlite+aiosqlite:////data/db.sqlite3
MEDIA_ROOT=/data/media
CORS_ORIGINS=https://<cloudfront-url>
GROQ_API_KEY=<your-groq-key>
GROQ_MODEL=llama-3.3-70b-versatile
# Optional ML: keep off unless you copied model files to /data/models.
ENABLE_ML_INFERENCE=False
VISION_MODEL_PATH=
VISION_CONF=0.25
VISION_IMGSZ=960
NLP_MODEL_PATH=
EOF
```

If enabling ML, copy the model files under `/data/models/` (mounted/persistent), set `VISION_MODEL_PATH` to the YOLO `.pt` file and `NLP_MODEL_PATH` to the local classifier directory; place `calibration.json` next to the classifier. The default `t2.micro` may not have enough RAM for PyTorch/Ultralytics; size the instance accordingly. With ML off, the image is still large but startup stays deterministic.

### 4. Start Backend
```bash
docker compose up -d --build
curl http://localhost:8000/api/health/
```

### 5. Add Nginx Proxy
```bash
sudo apt install -y nginx
# Proxy port 80 → 127.0.0.1:8000, client_max_body_size 55M
sudo systemctl enable nginx && sudo systemctl restart nginx
```

---

## Frontend → S3 + CloudFront

### 1. Build locally
```bash
echo VITE_API_URL=http://<ec2-public-ip> > .env.local
npm run build
```

### 2. S3 Bucket
- Create bucket (ap-south-1), unblock public access
- Enable Static Website Hosting: index document = `index.html`, error document = `index.html`
- Add public read bucket policy (s3:GetObject → *)

### 3. Upload
```bash
aws s3 sync dist/ s3://<bucket-name>/ --delete
```

### 4. CloudFront
- Origin: S3 website endpoint (not bucket URL)
- Redirect HTTP → HTTPS
- Custom error pages: 403/404 → /index.html (HTTP 200) for React routing
- Note CloudFront URL → update `CORS_ORIGINS` in EC2 `.env` → restart backend

---

## GitHub repo
`https://github.com/akcodes-py/Instant-Mechanic-AI-Diagonistic-Bot`

## After Deployment — Test
- Frontend: `https://<cloudfront-url>`
- Backend: `http://<ec2-ip>/api/health/`
- Submit: https://forms.gle/Q82YpwYYhoZJTMTg6
