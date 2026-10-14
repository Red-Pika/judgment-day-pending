# Desain Sistem: Tax Recon AI

## 1. Tujuan

1. Mencocokkan dua sumber dokumen pajak (contoh: Faktur Pajak vs Laporan Penjualan) dan menemukan selisih angka dengan **akurat dan dapat ditelusuri**.
2. Menjelaskan penyebab selisih dalam bahasa manusia dan menyarankan tindak lanjut.
3. Menyediakan chatbot untuk bertanya jawab atas hasil rekonsiliasi.

Di luar cakupan: pelaporan SPT, keputusan perlakuan fiskal, OCR dokumen scan (lihat roadmap).

## 2. Prinsip desain

| Prinsip | Penerapan |
|---|---|
| **LLM tidak menghitung angka** | Pencocokan dan selisih dihitung `src/core.js` (deterministik, diuji). LLM hanya menerima angka final untuk dijelaskan |
| **AI tidak menulis SQL** | Chatbot memakai 3 tool dengan query tetap dan terparameter. AI hanya mengisi nilai parameter |
| **Jejak audit** | Setiap proses punya `run_id`; setiap baris hasil menyimpan nilai A, nilai B, selisih, catatan, dan nomor baris file asal |
| **Hak akses minimal** | IAM hanya `bedrock:InvokeModel`; user Postgres read-only untuk tool chatbot; endpoint dilindungi autentikasi |
| **Satu sumber kebenaran** | Logika, config, dan prompt ada di `src/`, `config/`, `prompts/`; JSON workflow dibangkitkan dari sana (`npm run build:n8n`) sehingga tidak bisa berbeda dengan yang diuji |
| **Gagal dengan aman** | Jika LLM gagal, hasil hitung tetap dikembalikan dan disimpan (node penjelasan memakai `continueRegularOutput`) |

## 3. Arsitektur

![Arsitektur](img/architecture.png)

| Komponen | Peran | Catatan |
|---|---|---|
| Caddy | Reverse proxy + HTTPS otomatis | Profile `prod` di docker-compose |
| n8n | Orkestrasi dua workflow | Self-host Docker, database Postgres |
| PostgreSQL | Hasil rekonsiliasi, riwayat proses, memori chat | Satu server, database `n8n` dan `taxrecon` |
| Amazon Bedrock | LLM untuk penjelasan dan chatbot | Akses model diaktifkan per region |
| `web/chat.html` | Antarmuka chat | Statis; bisa di GitHub Pages/S3 |

## 4. Alur rekonsiliasi (Workflow 1)

![Alur rekonsiliasi](img/sequence-recon.png)

Poin penting: simpan hasil ke database dan panggilan LLM berjalan **paralel** setelah hitung selesai. Hanya maksimal 50 selisih terbesar yang dikirim ke LLM untuk membatasi biaya dan token.

## 5. Alur chatbot (Workflow 2)

![Alur chatbot](img/sequence-chat.png)

Tool yang tersedia untuk Agent:

| Tool | Fungsi | Parameter dari AI |
|---|---|---|
| `ringkasan_terakhir` | Ringkasan dan penjelasan proses terbaru | tidak ada |
| `cari_selisih` | Daftar dokumen bermasalah, urut selisih terbesar | `status`, `jumlah_baris` |
| `cari_dokumen` | Cari dokumen dari sebagian nomor faktur | `potongan_nomor` |

Semua tool hanya membaca proses **terbaru** dan memakai `$1::text` / `$2::int` (bukan interpolasi string).

## 6. Model data

![ERD](img/erd.png)

`recon_results.run_id` sengaja tanpa foreign key agar penyimpanan hasil dan ringkasan boleh berjalan paralel. Tabel `n8n_chat_histories` dibuat otomatis oleh node memori n8n.

## 7. Keputusan desain

| Keputusan | Alternatif | Alasan |
|---|---|---|
| Hitung di node Code | Hitung di SQL / minta LLM | Mudah diuji unit, satu sumber logika, tanpa halusinasi angka |
| Kode di-embed ke JSON via script | Salin-tempel manual | Menghindari beda versi antara yang diuji dan yang dijalankan |
| Tool SQL tetap | Agent bebas menulis SQL | Menutup risiko SQL injection dan kebocoran tabel lain |
| Tanpa foreign key run_id | FK ke recon_runs | Penyimpanan paralel di workflow 1 |
| Upload CSV via webhook | Form Trigger | Nama properti binary deterministik (`fileA`, `fileB`) |
| Basic Auth di chat | Tanpa auth | Chatbot membaca data pajak, tidak boleh terbuka |

## 8. Ancaman dan mitigasi

| Ancaman | Mitigasi |
|---|---|
| Orang tak berwenang membaca data lewat chat | Basic Auth di Chat Trigger, HTTPS, `allowedOrigins` dibatasi ke domain halaman chat |
| Orang tak berwenang mengunggah data | Header Auth di webhook upload |
| Prompt injection lewat isi dokumen | AI tidak punya tool tulis; tool hanya SELECT terparameter; angka final dari kode |
| SQL injection | Query terparameter; ada tes payload injection |
| XSS lewat jawaban AI di halaman chat | Teks di-escape sebelum diformat; ada tes di browser |
| Kebocoran kredensial | Credential disimpan terenkripsi n8n (`N8N_ENCRYPTION_KEY`); `.env` di-gitignore |
| Data asli ikut ter-commit | `.gitignore` memblokir `data/`, `*.xlsx`, `.env` |
| Biaya Bedrock membengkak | Batas 50 baris per proses, `maxTokensToSample`, AWS Budgets |

## 9. Mode kegagalan

| Kegagalan | Perilaku |
|---|---|
| Kolom CSV tidak ditemukan | Error jelas yang menyebut kolom tersedia |
| Angka/tanggal tidak valid pada satu baris | Baris dilewati, masuk `warnings` pada respons |
| Bedrock error/akses model belum aktif | Respons tetap berisi hasil hitung; penjelasan berisi pesan fallback |
| Postgres tidak tersedia | Respons tetap dikembalikan, tetapi hasil tidak tersimpan (periksa eksekusi n8n) |

## 10. Batas dan skala

- File sangat besar: batas payload n8n (`N8N_PAYLOAD_SIZE_MAX`, bawaan 16 MB) dan memori node Code. Untuk puluhan ribu baris, pindahkan pencocokan ke SQL atau proses bertahap.
- Penyimpanan hasil per baris (satu INSERT per item) cukup untuk ribuan baris; untuk skala besar gunakan batch insert.
- Satu instance n8n; untuk skala besar gunakan queue mode + ECS/Fargate + RDS.

## 11. Roadmap

1. Dukungan `.xlsx` langsung dan PDF/scan (Textract atau Bedrock vision + review manual).
2. Laporan Excel otomatis dan notifikasi Telegram/Slack.
3. RAG atas peraturan dan SOP internal (pgvector + Titan Embeddings).
4. Login per pengguna (SSO) menggantikan Basic Auth bersama.
