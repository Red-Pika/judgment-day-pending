# Konfigurasi n8n

> Nama menu dan label di antarmuka n8n bisa sedikit berbeda antar versi. Bila ada node bertanda merah setelah import, buka node tersebut dan pilih credential/model yang diminta.

## 1. Environment variable (docker-compose)

| Variabel | Nilai | Fungsi |
|---|---|---|
| `DB_TYPE` | `postgresdb` | n8n memakai Postgres, bukan SQLite |
| `DB_POSTGRESDB_*` | host `postgres`, db `n8n` | Koneksi database n8n |
| `N8N_ENCRYPTION_KEY` | string acak (`openssl rand -hex 24`) | Enkripsi credential. **Simpan; jangan diganti setelah dipakai** |
| `N8N_HOST`, `N8N_PROTOCOL`, `WEBHOOK_URL` | domain Anda + `https` | URL webhook yang dihasilkan n8n |
| `GENERIC_TIMEZONE`, `TZ` | `Asia/Jakarta` | Zona waktu |
| `N8N_DEFAULT_BINARY_DATA_MODE` | `filesystem` | File upload tidak menumpuk di memori |
| `EXECUTIONS_DATA_PRUNE` | `true` | Hapus riwayat eksekusi lama (isinya bisa memuat data pajak) |
| `EXECUTIONS_DATA_MAX_AGE` | `168` (jam) | Retensi riwayat eksekusi |
| `N8N_PAYLOAD_SIZE_MAX` | bawaan 16 (MB) | Naikkan bila file CSV lebih besar |

## 2. Credentials

| Nama (disarankan) | Tipe | Isian | Dipakai oleh |
|---|---|---|---|
| `Postgres - taxrecon` | Postgres | Host `postgres`, Database `taxrecon`, user & password dari `.env`, SSL sesuai lingkungan | Save Results, Save Run, Postgres Chat Memory |
| `Postgres - taxrecon (read-only)` | Postgres | Sama, tetapi user `chatbot_ro` (lihat `db/init.sql`) | 3 tool SQL chatbot (disarankan) |
| `AWS - Bedrock` | AWS | Access key ID, secret, **region** tempat model diaktifkan | Bedrock Chat Model (2 workflow) |
| `Header Auth - Upload` | Header Auth | Name `X-API-Key`, Value = kunci acak | Webhook Upload |
| `Basic Auth - Chatbot` | Basic Auth | Username dan password untuk login chat | Chat Trigger |

> Credential di file JSON hanya berisi placeholder `GANTI_DENGAN_CREDENTIAL_ANDA`. Setelah import, pilih credential di tiap node.

## 3. Workflow 1: Rekonsiliasi

| # | Node | Tipe | Konfigurasi kunci |
|---|---|---|---|
| 1 | Webhook Upload | Webhook | `POST`, path `tax-recon`, Authentication **Header Auth**, Respond **Using 'Respond to Webhook' Node** |
| 2 | Parse and Reconcile | Code | JavaScript, *Run Once for All Items*. Isi dibangkitkan dari `src/core.js`; jangan diedit manual |
| 3 | Split Results | Split Out | Field `results` |
| 4 | Save Results | Postgres | Insert ke `public.recon_results`, *Auto-map input data* |
| 5 | Build Prompt | Code | Ambil maks 50 selisih terbesar, susun prompt |
| 6 | Ada Selisih? | If | `discrepancy_count` > 0 (true: ke AI, false: langsung Assemble) |
| 7 | Explain Discrepancies | Basic LLM Chain | Prompt `={{ $json.prompt }}`; pesan sistem dari `prompts/explain_discrepancy.md`; *On Error: Continue* |
| 8 | Bedrock Chat Model | AWS Bedrock Chat Model | **Pilih model**; temperature 0.1; max tokens 2000 |
| 9 | Assemble | Code | Gabung hasil hitung + penjelasan (fallback bila AI gagal) |
| 10 | Respond | Respond to Webhook | JSON, body `={{ $json }}` |
| 11 | Prep Run Row | Code | Ubah `summary` menjadi string JSON |
| 12 | Save Run | Postgres | Insert ke `public.recon_runs` |

Parameter opsional di request: `tolerance` (Rp), `ppnRate` (misal `0.11`), `locale` (`id`/`en`/`auto`).

```bash
curl -X POST https://DOMAIN/webhook/tax-recon \
  -H "X-API-Key: KUNCI_ANDA" \
  -F fileA=@sample-data/faktur_pajak.csv \
  -F fileB=@sample-data/laporan_penjualan.csv \
  -F tolerance=10
```

## 4. Workflow 2: Chatbot

| # | Node | Tipe | Konfigurasi kunci |
|---|---|---|---|
| 1 | Chat Trigger | Chat Trigger | *Make Chat Publicly Available* = ON, Mode **Embedded Chat**, Authentication **Basic Auth**, Allowed Origins = domain halaman chat |
| 2 | AI Agent | AI Agent | Pesan sistem dari `prompts/chatbot_system.md`; max iterations 6 |
| 3 | Bedrock Chat Model | AWS Bedrock Chat Model | Pilih model; temperature 0.1 |
| 4 | Postgres Chat Memory | Postgres Chat Memory | Tabel `n8n_chat_histories`, context window 10, session dari input chat |
| 5 | ringkasan_terakhir | Postgres Tool | Execute Query (tanpa parameter) |
| 6 | cari_selisih | Postgres Tool | Execute Query, Query Replacement `[status, jumlah_baris]` dari `$fromAI` |
| 7 | cari_dokumen | Postgres Tool | Execute Query, Query Replacement `[potongan_nomor]` dari `$fromAI` |

Setelah **Activate**, salin *Production URL* di node Chat Trigger ke `web/chat.html`. Sebelum diaktifkan, URL yang tersedia hanyalah *Test URL*, dan itu tidak boleh dipakai untuk produksi.

## 5. Memilih model Bedrock

1. Konsol Bedrock, *Model access*: aktifkan model di region yang sama dengan credential AWS.
2. Di node Bedrock Chat Model, buka daftar *Model* dan pilih model tersebut. Beberapa model baru hanya bisa dipanggil lewat *inference profile*; bila muncul error "on-demand throughput isn't supported", pilih opsi inference profile (ID berawalan region, misal `us.`).
3. Pakai model yang sama di kedua workflow agar perilakunya konsisten, atau model lebih kecil untuk chat bila ingin hemat.

## 6. Checklist aktivasi

- [ ] `.env` terisi, `docker compose up -d`, semua container `running`
- [ ] 5 credential dibuat dan terpasang di node-nya
- [ ] Model Bedrock dipilih di 2 node Bedrock Chat Model
- [ ] Workflow 1 **Active**; `curl` sampel mengembalikan JSON dengan `summary`
- [ ] `SELECT status, COUNT(*) FROM recon_results GROUP BY status;` menunjukkan 7 status
- [ ] Workflow 2 **Active**; URL produksi dipasang di `web/chat.html`
- [ ] Login salah di chat ditolak, login benar mendapat jawaban

## 7. Pemecahan masalah

| Gejala | Kemungkinan penyebab | Solusi |
|---|---|---|
| Webhook 404 | Workflow belum Active, atau memakai Test URL | Aktifkan; pakai Production URL |
| 401/403 saat upload atau chat | Header/Basic Auth tidak cocok | Samakan dengan credential di n8n |
| Chat: "Tidak bisa terhubung" | URL salah, bukan HTTPS dari halaman HTTPS, atau CORS | Cek URL; gunakan HTTPS; isi *Allowed Origins* dengan domain halaman |
| `AccessDeniedException` dari Bedrock | Akses model belum diaktifkan / region beda / IAM kurang | Aktifkan *Model access*; samakan region; cek kebijakan IAM |
| Error "kolom ... tidak ditemukan" | Nama kolom CSV beda dengan `config/mapping.json` | Sesuaikan mapping lalu `npm run build:n8n` dan import ulang |
| Respons `ai_explanation` berisi "tidak tersedia" | Bedrock gagal; hasil hitung tetap valid | Lihat eksekusi node Explain Discrepancies |
| Chatbot menjawab "data tidak ditemukan" | Workflow 1 belum pernah dijalankan | Jalankan upload sampel terlebih dahulu |
| Tool SQL gagal pada `$1` | Query Replacement kosong/format salah | Pastikan berupa array `[ ... ]` dari `$fromAI` |
| Credential hilang setelah restart | `N8N_ENCRYPTION_KEY` berubah | Kembalikan kunci semula |
