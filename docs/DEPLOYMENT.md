# Deployment

## Architecture
- **Frontend:** AWS S3 (static hosting) + CloudFront (CDN + HTTPS)
- **Backend:** AWS EC2 t2.micro (Ubuntu) + Docker Compose + Nginx

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
DJANGO_SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<ec2-ip>
CORS_ALLOWED_ORIGINS=https://<cloudfront-url>
SQLITE_PATH=/data/db.sqlite3
MEDIA_ROOT=/data/media
GROQ_API_KEY=<your-groq-key>
GROQ_MODEL=qwen/qwen3.8-27b
ENFORCE_HTTPS=False
EOF
```

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
- Note CloudFront URL → update `CORS_ALLOWED_ORIGINS` in EC2 .env → restart backend

---

## GitHub repo
`https://github.com/akcodes-py/Instant-Mechanic-AI-Diagonistic-Bot`

## After Deployment — Test
- Frontend: `https://<cloudfront-url>`
- Backend: `http://<ec2-ip>/api/health/`
- Submit: https://forms.gle/Q82YpwYYhoZJTMTg6
