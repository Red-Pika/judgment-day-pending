# Evidence Pengujian Chatbot: tax-recon-ai

| | |
|---|---|
| **Proyek / pemilik repo** | Red-Pika / `tax-recon-ai` |
| **Waktu eksekusi** | 2026-10-14 08:59:43 UTC |
| **Lingkungan** | Node.js v22.22.2, Chromium 141.0.7390.37 (Playwright), SQLite 3.45.1, Linux sandbox |
| **Dijalankan oleh** | Claude (Anthropic) di sandbox, **bukan** di mesin atau akun AWS milik Red-Pika |

SHA-256 berkas yang diuji (untuk memastikan yang Anda jalankan sama dengan yang diuji):

```
c3bbb326337c34c56c505bafd12a50f025589104ccbdafe55db06ff219e88b04  src/core.js
2c45e969d0730815f31011661f2d3fe8afef991b3569ebf5d7a2f34bfdf38897  n8n/workflow-1-rekonsiliasi.json
69a8678726f2dc6a9d2bc76ae435f4da57df9e8a2c03b105e29e27d26fd7b91f  n8n/workflow-2-chatbot.json
07bf07124b97f5edb3155522d751dd82cf7e44cfd4b77eb236d18e2d845975db  web/chat.html
```

Semua output di bawah disalin otomatis dari eksekusi nyata, tidak diketik manual.


> **Baca dulu.** Ini bukti untuk *antarmuka chat* dan *logika tool SQL*. Ini **bukan** bukti bahwa chatbot sudah menjawab lewat n8n + AWS Bedrock sungguhan. Bagian itu belum diuji dan tercantum di bagian 5.

## 1. Antarmuka web chat di browser sungguhan (14/14 lolos)

`web/chat.html` dibuka di Chromium dan dihubungkan ke **mock server** (`tests/e2e/mock-n8n.js`) yang meniru kontrak Chat Trigger n8n (Basic Auth, body `action/sessionId/chatInput`, balasan `{"output": "..."}`). Jawaban mock berasal dari hasil rekonsiliasi nyata (`src/core.js`) memakai template, **bukan dari LLM**.

```
PASS Halaman chat tampil setelah login
PASS Password dikosongkan dari form setelah login
PASS Jawaban ringkasan muncul
PASS Jawaban 5 selisih terbesar memuat faktur ...99 (terbesar)
PASS Format tebal/kode dirender (bukan tanda * atau `)
PASS Tidak ada elemen <img> berbahaya di DOM
PASS Skrip tidak tereksekusi (window.__xss kosong)
PASS Login salah menampilkan pesan 'Login ditolak'
PASS Server mati menampilkan pesan koneksi
PASS Semua request sukses membawa header Basic Auth yang benar
PASS Body memakai kontrak n8n (action=sendMessage, sessionId, chatInput)
PASS Content-Type application/json
PASS sessionId konsisten dalam satu percakapan (memori Postgres bergantung ini)  [1 sessionId unik]
PASS Request login salah ditolak server (authOk=false tercatat)

14/14 lolos
```

Tangkapan layar (mode terang, login benar, dua pertanyaan dari tombol saran):

![Chat sukses](evidence/chat-sukses-light.png)

Tangkapan layar (mode gelap, password salah ditolak):

![Login salah](evidence/chat-login-salah-dark.png)

Contoh request yang diterima server dari halaman chat (hasil rekam otomatis):

```json
{
  "authOk": true,
  "contentType": "application/json",
  "body": {
    "action": "sendMessage",
    "sessionId": "071f8dbc-f098-4985-98f4-c776a6834a1b",
    "chatInput": "Ringkasan rekonsiliasi terakhir"
  }
}
```

Request dengan password salah juga terekam dengan `authOk: false` dan dijawab 401, lalu halaman menampilkan pesan "Login ditolak".

## 2. Logika 3 tool SQL chatbot (13/13 lolos, di SQLite)

Query diambil **apa adanya dari `n8n/workflow-2-chatbot.json`**, diterjemahkan mekanis ke SQLite (`$1` jadi `:p1`, `ILIKE` jadi `LIKE`, buang `::text`/`::int`), lalu dijalankan pada data nyata hasil rekonsiliasi sampel plus satu run lama sebagai jebakan (harus diabaikan).

```
PASS ringkasan_terakhir mengembalikan 1 baris run TERBARU  [NEW]
PASS cari_selisih SEMUA: hanya run terbaru (INV-LAMA-9999 tidak muncul)
PASS cari_selisih SEMUA: MATCH murni tidak ikut, jumlah = 6  [6 baris]
PASS cari_selisih: urut selisih terbesar ke terkecil  [[16650000, 4440000, 3330000, 555000, 5, 0]]
PASS cari_selisih: peringkat 1 = faktur ...99 (ONLY_IN_B)
PASS cari_selisih filter ONLY_IN_A -> 1 baris
PASS cari_selisih LIMIT 2 -> 2 baris
PASS cari_selisih status tidak dikenal -> 0 baris (tidak error)
PASS cari_dokumen '0002' -> 1 dokumen AMOUNT_MISMATCH
PASS cari_dokumen sebagian nomor '26.09000006' -> DUPLICATE_KEY
PASS cari_dokumen tidak menemukan data lama (INV-LAMA)
PASS cari_dokumen payload SQL injection -> 0 baris
PASS Tabel recon_results masih utuh setelah payload injection

13/13 lolos
```

Yang dibuktikan: hanya run terbaru yang dibaca, urutan selisih terbesar, filter status dan limit bekerja, pencarian dokumen sebagian nomor bekerja, dan payload SQL injection tidak menghapus tabel. **Tidak dibuktikan:** kompatibilitas sintaks/tipe Postgres (lihat bagian 5).

## 3. Struktur workflow chatbot dan konfigurasi keamanan

```
✔ workflow 1: id & nama node unik, semua koneksi valid (1.098482ms)
✔ workflow 2: id & nama node unik, semua koneksi valid (0.241009ms)
✔ workflow 1: webhook upload wajib Header Auth (1.297153ms)
✔ workflow 2: chat trigger publik tetapi wajib Basic Auth (0.19525ms)
✔ workflow 2: agent terhubung ke model, memori, dan 3 tool (0.402022ms)
✔ workflow 2: tool SQL terparameter, tanpa interpolasi, jumlah $n = jumlah nilai (0.525577ms)
✔ kode node Code workflow 1 berjalan end-to-end dengan data contoh (6.776728ms)
✔ Assemble: tanpa selisih -> teks default; AI gagal -> pesan fallback (1.279085ms)
```

Ini memeriksa antara lain: Chat Trigger wajib Basic Auth, Agent terhubung ke 1 model + 1 memori + 3 tool, query tool tidak berisi interpolasi `{{ }}`, jumlah `$n` sama dengan jumlah nilai `$fromAI`, dan tidak ada perintah tulis (INSERT/UPDATE/DELETE/DROP) pada tool.

## 4. Seluruh rangkaian tes otomatis: 18/18 lolos

```
✔ parseAmount: format Indonesia (1.253844ms)
✔ parseAmount: locale en & auto (0.345656ms)
✔ parseAmount: input tidak valid melempar error (0.287032ms)
✔ parseDate (0.394533ms)
✔ normalisasi NPWP & nomor faktur (0.277134ms)
✔ parseCsv: kutip, delimiter ; dan nomor baris (1.714355ms)
✔ rekonsiliasi data contoh menghasilkan status yang benar (2.060963ms)
✔ toleransi 0 membuat selisih pembulatan menjadi mismatch (0.72904ms)
✔ kolom yang tidak ada memberi pesan error yang jelas (0.777635ms)
✔ cek tarif PPN opsional menambah catatan (0.9507ms)
✔ workflow 1: id & nama node unik, semua koneksi valid (1.098482ms)
✔ workflow 2: id & nama node unik, semua koneksi valid (0.241009ms)
✔ workflow 1: webhook upload wajib Header Auth (1.297153ms)
✔ workflow 2: chat trigger publik tetapi wajib Basic Auth (0.19525ms)
✔ workflow 2: agent terhubung ke model, memori, dan 3 tool (0.402022ms)
✔ workflow 2: tool SQL terparameter, tanpa interpolasi, jumlah $n = jumlah nilai (0.525577ms)
✔ kode node Code workflow 1 berjalan end-to-end dengan data contoh (6.776728ms)
✔ Assemble: tanpa selisih -> teks default; AI gagal -> pesan fallback (1.279085ms)
ℹ tests 18
ℹ suites 0
ℹ pass 18
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 172.321562
```

Data rekonsiliasi yang mendasari jawaban chat (`npm run recon`):

```csv
status,invoice_no,npwp,date_a,date_b,dpp_a,dpp_b,diff_dpp,ppn_a,ppn_b,diff_ppn,notes,row_a,row_b
MATCH,010.000-26.09000001,0012345678901000,2026-09-03,2026-09-03,10000000,10000000,0,1100000,1100000,0,,2,2
AMOUNT_MISMATCH,010.000-26.09000002,0023456789012000,2026-09-05,2026-09-05,25000000,24500000,500000,2750000,2695000,55000,"DPP berbeda 500000; PPN berbeda 55000",3,3
MATCH_ROUNDING,010.000-26.09000003,0034567890123000,2026-09-10,2026-09-10,7500000,7500000,0,825000,824995,5,"Selisih pembulatan (DPP 0, PPN 5)",4,4
ONLY_IN_A,010.000-26.09000004,0012345678901000,2026-09-28,,4000000,,4000000,440000,,440000,Tidak ditemukan di sumber B,5,
PERIOD_MISMATCH,010.000-26.09000005,0045678901234000,2026-09-30,2026-10-02,12000000,12000000,0,1320000,1320000,0,Masa berbeda: A 2026-09 vs B 2026-10,6,5
DUPLICATE_KEY,010.000-26.09000006,0056789012345000,2026-09-12,2026-09-12,3000000,6000000,-3000000,330000,660000,-330000,"Kunci muncul 1x di A dan 2x di B (nilai dijumlahkan); Total berbeda melebihi toleransi",7,6
ONLY_IN_B,010.000-26.09000099,0067890123456000,,2026-09-20,,15000000,-15000000,,1650000,-1650000,Tidak ditemukan di sumber A,,8
```

## 5. Yang TERBUKTI dan yang BELUM

| Komponen chatbot | Status | Keterangan |
|---|---|---|
| Tampilan chat, tombol saran, mode terang/gelap | Terbukti | Browser sungguhan + tangkapan layar |
| Login, pesan error 401, server mati | Terbukti | Terhadap mock |
| Pengiriman `sessionId` konsisten, format body | Terbukti | Terhadap mock |
| Escape HTML (anti-XSS) di jawaban | Terbukti | Browser sungguhan |
| Logika query tool (filter, urutan, run terbaru, anti-injection) | Terbukti | Di SQLite, bukan Postgres |
| Struktur workflow dan konfigurasi auth | Terbukti | Tes otomatis |
| **Kontrak asli Chat Trigger n8n** | **Belum terbukti** | Mock dibuat dari pemahaman saya atas kontrak; belum dicocokkan dengan n8n sungguhan |
| **Sintaks query di PostgreSQL** | **Belum terbukti** | Perlu dijalankan di Postgres |
| **AI Agent memanggil tool yang tepat dan menjawab benar** | **Belum terbukti** | Butuh n8n + Bedrock aktif |
| **Memori percakapan (`n8n_chat_histories`)** | **Belum terbukti** | Butuh n8n + Postgres |
| **CORS/HTTPS di server sungguhan** | **Belum terbukti** | Butuh deploy |

## 6. Cara membuat bukti sungguhan (tangkap layar dan simpan)

1. Jalankan sesuai `docs/N8N-CONFIG.md` bagian 6 (checklist aktivasi).
2. Buka `web/chat.html` dengan `?url=<Production URL>`, login, lalu tanyakan:
   - "Ringkasan rekonsiliasi terakhir" (harus menyebut 6 dokumen A, 7 dokumen B, 5 perlu tindak lanjut).
   - "Tampilkan 5 selisih terbesar" (urutan teratas faktur `...99`, ONLY_IN_B, DPP -15.000.000).
   - "Cek faktur yang berakhiran 0002" (DPP berbeda 500.000, PPN 55.000).
3. Di n8n, buka **Executions** dan tangkap layar eksekusi yang menunjukkan AI Agent memanggil tool `cari_selisih`/`cari_dokumen` dengan hasil dari Postgres. Itu bukti paling kuat bahwa angka berasal dari database.
4. Coba login salah dan pastikan ditolak.

Jika jawaban chat sungguhan cocok dengan angka di atas, chatbot terbukti berfungsi end-to-end.
