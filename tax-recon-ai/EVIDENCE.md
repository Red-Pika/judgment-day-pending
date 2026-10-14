# Evidence Pengujian Rekonsiliasi: tax-recon-ai

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


## 1. Seluruh tes otomatis: 18/18 lolos

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

## 2. Eksekusi rekonsiliasi pada data contoh

Perintah: `npm run recon`

```
Dokumen A: 6 | Dokumen B: 7 | Toleransi: Rp 10
Cocok: 28.57% dari 7 kunci

┌─────────────────┬────────┐
│ (index)         │ Values │
├─────────────────┼────────┤
│ MATCH           │ 1      │
│ MATCH_ROUNDING  │ 1      │
│ AMOUNT_MISMATCH │ 1      │
│ PERIOD_MISMATCH │ 1      │
│ ONLY_IN_A       │ 1      │
│ ONLY_IN_B       │ 1      │
│ DUPLICATE_KEY   │ 1      │
└─────────────────┴────────┘
Selisih total DPP (A-B): -13500000
Selisih total PPN (A-B): -1484995

Hasil disimpan di: /home/claude/tax-recon-ai/output
```

Berkas hasil `output/hasil_rekonsiliasi.csv`:

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

Pemeriksaan manual atas data contoh, sesuai ekspektasi:
- `...0002`: DPP A 25.000.000 vs B 24.500.000, selisih **500.000**; PPN selisih **55.000**, status `AMOUNT_MISMATCH`.
- `...0003`: PPN 825.000 vs 824.995, selisih **5** dan masih dalam toleransi Rp10, status `MATCH_ROUNDING`.
- `...0005`: nominal sama tetapi bulan beda (09 vs 10), status `PERIOD_MISMATCH`.
- `...0006`: muncul 2x di B, status `DUPLICATE_KEY`.
- `...0001`: nomor faktur dan NPWP beda format penulisan tetapi tetap cocok (`MATCH`) berkat normalisasi.

## 3. Yang TERBUKTI dan yang BELUM

| Komponen | Status |
|---|---|
| Logika rekonsiliasi (`src/core.js`) | Terbukti, tes + eksekusi nyata |
| Kode di dalam node Code n8n | Terbukti lewat simulasi |
| Struktur JSON workflow, koneksi, konfigurasi auth | Terbukti (tes otomatis) |
| Skema database cocok dengan kolom hasil | Terbukti (tes otomatis) |
| Evidence chatbot | Lihat `EVIDENCE-CHATBOT.md` |
| **Import ke n8n sungguhan** | **Belum diuji** |
| **Panggilan ke AWS Bedrock** | **Belum diuji** |
| **Deploy di EC2/Docker** | **Belum diuji** |

Checklist untuk membuat bukti sungguhan ada di `docs/N8N-CONFIG.md` bagian 6 dan `EVIDENCE-CHATBOT.md` bagian 6.
