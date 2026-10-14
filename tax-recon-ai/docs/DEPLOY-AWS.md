# Deploy di AWS (EC2 + Docker)

## 1. Siapkan Bedrock
1. Pilih region yang mendukung model yang Anda butuhkan (dan sesuai kebijakan lokasi data perusahaan).
2. Bedrock, **Model access**: minta/aktifkan akses ke model.
3. IAM, buat user khusus dengan kebijakan `aws/iam-policy-bedrock.json` (persempit `Resource` ke model/inference profile yang dipakai bila memungkinkan), lalu buat access key untuk credential n8n.

## 2. Server
- EC2 (mis. 2 vCPU / 4 GB RAM untuk mulai), Ubuntu LTS, disk terenkripsi (EBS encryption).
- Security Group: buka **80 & 443** saja ke publik; **22 (SSH) hanya dari IP Anda**. Jangan membuka 5678 dan 5432.
- Pasang Docker + Docker Compose plugin.

## 3. Jalankan
```bash
git clone <repo-anda> tax-recon-ai && cd tax-recon-ai
cp .env.example .env && nano .env      # isi N8N_DOMAIN, N8N_HOST, N8N_PROTOCOL=https, WEBHOOK_URL, password, N8N_ENCRYPTION_KEY
docker compose --profile prod up -d
```
Arahkan DNS (A record) domain ke IP publik EC2. Caddy akan menerbitkan sertifikat HTTPS otomatis.

## 4. Pengamanan
- n8n: aktifkan user owner di login pertama; webhook produksi diberi **Header Auth**.
- Postgres: gunakan user `chatbot_ro` (read-only) untuk tool SQL chatbot.
- Backup: jadwalkan snapshot EBS dan `pg_dump` ke S3 (bucket terenkripsi, tanpa akses publik).
- Biaya: pasang **AWS Budgets** dengan alert, dan batasi `maxTokensToSample` di node Bedrock.
- Log: jangan menulis isi dokumen pajak ke log; atur retensi eksekusi n8n (`EXECUTIONS_DATA_MAX_AGE`).

## 5. Alternatif skala lebih besar
ECS/Fargate untuk n8n, RDS PostgreSQL untuk database, ALB + ACM untuk HTTPS, Secrets Manager untuk rahasia, dan S3 untuk file masuk/keluar.
