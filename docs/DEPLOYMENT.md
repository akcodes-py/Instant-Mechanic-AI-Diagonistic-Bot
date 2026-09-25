# Deployment

## Frontend → Vercel (free tier)
1. Push `instant-mechanic/` to GitHub.
2. Vercel → New Project → import repo, root = repo root, framework = Vite.
3. Build: `npm run build`, output `dist`.
4. Env: `VITE_API_URL=https://<backend-url>` (no secrets).
5. Deploy. Custom domain `instantmechanic.online` optional via Vercel domains (HTTPS automatic).

## Backend → AWS (free-tier-eligible, verify account)
Recommended: EC2 t2/t3.micro (free tier) + Docker.
1. EC2 Ubuntu, security group 80/443/22. Attach EBS for `/data` (note: Docker volumes are host-local; for multi-AZ persistence use EFS/EBS snapshots — volume ≠ automatic durability).
2. Install Docker + Compose plugin. Copy repo, create `/data`, set env via systemd/ENV (never bake secrets):
   `DJANGO_SECRET_KEY, DJANGO_DEBUG=False, DJANGO_ALLOWED_HOSTS=<api-domain>, CORS_ALLOWED_ORIGINS=https://<vercel-url>, SQLITE_PATH=/data/db.sqlite3, MEDIA_ROOT=/data/media, GROQ_API_KEY=<secret>, ENFORCE_HTTPS=True`
3. `docker compose up -d --build`. Behind ALB/NGINX with ACM cert for HTTPS; `SECURE_SSL_REDIRECT` is on when `DEBUG=False`.
4. Alternative: App Runner / Elastic Beanstalk with same image (`Dockerfile.backend`); mount EFS for `/data` if SQLite must survive restarts (SQLite is per assignment; Postgres would need code change — not done).

## Remaining manual steps (not done here)
- Create GitHub repo + push; add Vercel/AWS credentials; DNS; verify free-tier eligibility; set `GROQ_API_KEY` in host env; back up `/data/db.sqlite3`.
