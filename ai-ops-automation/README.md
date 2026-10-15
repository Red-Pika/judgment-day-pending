# AI-Assisted IT Operations Automation

> **Status proyek:** proyek portofolio / proof-of-concept. Bukan sistem produksi dan bukan pengalaman kerja.
> Eksekusi perintah **sengaja hanya dry-run**. Evidence di `evidence/` dihasilkan dari simulasi lokal
> dengan LLM **mock**; jalur Claude API sungguhan sudah diimplementasikan dan di-unit-test, tetapi belum
> dijalankan live di repo ini (lihat bagian "Menjalankan dengan Claude API" dan "Batasan").

Alert monitoring → **n8n** (orkestrasi) → **layanan guardrail** (validasi, redaksi, LLM, policy, approval, audit) → laporan di chat.

```
Alert fires ─► n8n Webhook ─► POST /triage ─► laporan ke chat
                                  │
        validasi ► redaksi ► LLM (Claude) ► validasi output ► policy risiko ► audit
                                                                   │
                                          langkah berisiko ► tiket approval ► n8n Wait ► dry-run
```

## Yang dibuktikan proyek ini
| Kebutuhan | Implementasi | Bukti |
|---|---|---|
| 1. Simulasi alert | `simulator/scenarios.py`, `simulator/send_alert.py` (5 skenario) | `evidence/summary.md` |
| 2. n8n menerima event & orkestrasi | `n8n/workflow.json` (webhook, retry, error branch, Wait for approval) | lihat "Menjalankan" |
| 3. Integrasi Claude/ChatGPT via API | `opsguard/llm.py` (`AnthropicProvider`, prompt, parsing JSON ketat, retry) | `tests/test_llm.py` |
| 4a. Validasi | `opsguard/validation.py` (whitelist field, batas ukuran) + validasi output LLM | `test_validation.py`, `test_llm.py` |
| 4b. Redaksi data sensitif | `opsguard/redaction.py` (input **dan** output LLM) | `test_redaction.py`, `evidence/secret_scan.txt` |
| 4c. Audit log | `opsguard/audit.py` (JSONL + hash chain, tamper-evident) | `evidence/audit.jsonl`, `audit_integrity_check.txt` |
| 4d. Persetujuan manusia | `opsguard/policy.py` + `approvals.py` (TTL, sekali pakai, subset langkah) | `evidence/approval_decisions.json` |
| 5. Dokumentasi | `docs/` | — |
| Notifikasi Telegram / Slack / Email | `opsguard/notify.py` + endpoint `POST /notify` | `evidence/notifications/`, `tests/test_notify.py` |

## Struktur
```
opsguard/     layanan guardrail (Python stdlib saja, tanpa dependensi)
n8n/          workflow.json (import ke n8n)
simulator/    skenario alert + pengirim
tests/        85 unit/integration test (termasuk notifikasi)
scripts/      generate_evidence.py
evidence/     hasil run nyata dari simulasi lokal
docs/         ARCHITECTURE.md, OPERATIONS.md (kegagalan & biaya), TEST_REPORT.md
```

## Menjalankan (tanpa Docker, tanpa API key)
```bash
python3 -m unittest discover -s tests -t . -v     # 85 test
python3 -m scripts.generate_evidence              # regenerasi evidence/
SERVICE_TOKEN=dev ENABLE_CHAT_SINK=1 python3 -m opsguard.app &
python3 -m simulator.send_alert --url http://localhost:8080/triage --scenario oom_checkout --token dev
```

## Menjalankan dengan n8n (Docker)
```bash
cp .env.example .env        # isi SERVICE_TOKEN
docker compose up --build
```
1. Buka http://localhost:5678 → **Import from file** → `n8n/workflow.json` → **Activate**.
2. `python3 -m simulator.send_alert --url http://localhost:5678/webhook/ops-alert --scenario oom_checkout`
3. Laporan masuk ke semua channel yang Anda isi di `.env` (Telegram/Slack/email); chat-sink lokal: `curl -H "X-Service-Token: $SERVICE_TOKEN" localhost:8080/_chat-sink`
4. Pesan "APPROVAL REQUIRED" berisi resume URL; setujui dengan
   `curl -X POST <resumeUrl> -H 'Content-Type: application/json' -d '{"decision":"approved","approver":"nama"}'`
5. **Ambil screenshot** canvas workflow, execution sukses, dan pesan chat → simpan di `evidence/screenshots/`.

> `workflow.json` belum saya jalankan di instance n8n (lingkungan pembuatan tidak punya n8n/Docker). Skema node
> mengikuti n8n 1.x; bila ada perbedaan versi, perbaiki di editor lalu export ulang.

## Notifikasi: Telegram, Slack, Email
n8n memanggil `POST /notify`; service mengirim ke **semua channel yang terkonfigurasi** (boleh lebih dari satu).
Channel aktif hanya bila konfigurasinya lengkap; satu channel gagal tidak menghalangi yang lain.

| Channel | Isi di `.env` | Cara mendapatkan |
|---|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Buat bot lewat @BotFather, kirim satu pesan ke bot, buka `https://api.telegram.org/bot<TOKEN>/getUpdates`, salin `chat.id` |
| Slack | `SLACK_WEBHOOK_URL` | api.slack.com/apps → Incoming Webhooks |
| Email | `SMTP_HOST/PORT/USER/PASSWORD`, `EMAIL_TO` | Gmail: `smtp.gmail.com`, 587, `starttls`, **App Password** (butuh 2-Step Verification; jangan pakai password akun) |

`EMAIL_TO` di `.env.example` sudah berisi `adhit.adhya01@gmail.com`. Jika repo ini publik, ganti dengan placeholder agar alamat Anda tidak ikut terpublikasi.

**Uji kirim sungguhan** (setelah mengisi `.env`):
```bash
set -a; . ./.env; set +a; python3 -m scripts.test_notify
```
Keamanan: teks diredaksi lagi sebelum dikirim, token/password dibuang dari pesan error, isi pesan tidak masuk audit log
(hanya channel & status). Jalur *failure* di n8n memanggil Telegram langsung, tidak lewat service, supaya kegagalan service
tetap terkabar. **Resume URL approval adalah "kunci"**: siapa pun yang memegangnya bisa menyetujui, jadi kirim hanya ke
chat/email privat. Peningkatan lanjutan: tombol inline Telegram/Slack dengan identitas approver terverifikasi.

## Menjalankan dengan Claude API
```bash
# .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-5-5            # cek nama model terbaru di dokumentasi Anthropic
PRICE_IN_PER_MTOK=...                 # isi dari halaman harga resmi
PRICE_OUT_PER_MTOK=...
```
Jalankan ulang skenario, lalu simpan laporan & `usage` nyata di `evidence/live/`. Hanya dengan itu klaim
"terintegrasi dengan Claude" punya bukti run sungguhan.

## Batasan yang jujur
- Evidence notifikasi memakai server tiruan lokal (Telegram/Slack = HTTP palsu, email = server SMTP palsu), **bukan** pengiriman nyata ke Telegram/Slack/Gmail. Pengiriman nyata baru terbukti setelah Anda menjalankan `scripts.test_notify` dengan kredensial sendiri.
- Evidence = LLM **mock** (deterministik). Latensi milidetik di tabel **bukan** latensi LLM sungguhan; target ~30 dtk pada diagram adalah SLO rencana.
- Eksekusi dry-run saja; tidak ada runner nyata. Approval disimpan in-memory (hilang saat restart); audit log tahan restart.
- Redaksi berbasis regex: tidak menangkap semua rahasia (mis. AWS secret key tanpa prefix, nama orang). Untuk produksi tambahkan DLP/scanner khusus.
- Policy default-deny berbasis allowlist, bukan sandbox. Perintah harus berbentuk `kubectl <verb> ...` (flag sebelum verb dianggap berisiko).
- Tidak ada dedup/rate limit per alert, tidak ada TLS di layanan (taruh di belakang reverse proxy), autentikasi = shared secret.
