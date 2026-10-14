# Proses & Aturan Pencocokan

## Alur Workflow 1 (Rekonsiliasi)

1. **Webhook Upload** menerima 2 file CSV (`fileA`, `fileB`) + opsi `tolerance`, `ppnRate`, `locale`.
2. **Parse and Reconcile** (Code, tanpa AI):
   1. Baca CSV (delimiter `,` `;` atau tab terdeteksi otomatis).
   2. Petakan kolom sesuai `config/mapping.json`.
   3. Normalisasi: angka (format Indonesia), tanggal, NPWP, nomor faktur.
   4. Cocokkan berdasarkan **kunci = nomor dokumen + NPWP**.
   5. Hitung selisih `A - B` untuk DPP dan PPN, beri status.
3. **Split Results, Save Results**: setiap baris hasil disimpan ke `recon_results`.
4. **Build Prompt, Ada Selisih?**: hanya jika ada selisih, maksimal 50 baris terbesar dikirim ke LLM.
5. **Explain Discrepancies** (Bedrock): menjelaskan kemungkinan penyebab dan tindak lanjut. Angka tidak diubah.
6. **Assemble, Respond, Save Run**: respon JSON dikirim, ringkasan dan penjelasan disimpan ke `recon_runs`.

## Normalisasi

| Data | Aturan |
|---|---|
| Angka | `10.000.000,50` jadi `10000000.5` (locale `id`). Mendukung `Rp`, minus, dan `(1.000)` sebagai negatif. Angka tidak valid: baris dilewati dan dicatat sebagai *warning* |
| Tanggal | `yyyy-mm-dd`, `dd/mm/yyyy`, `dd-mm-yyyy`, `dd.mm.yyyy` |
| NPWP | Hanya digit; 15 digit diberi awalan `0` agar setara 16 digit (asumsi, verifikasi) |
| Nomor faktur | Huruf besar, tanda baca & spasi dibuang (`010.000-26.09000001` sama dengan `0100002609000001`) |

## Penentuan status

```
hanya di A            -> ONLY_IN_A
hanya di B            -> ONLY_IN_B
kunci ganda (A atau B)-> DUPLICATE_KEY   (nilai dijumlahkan lalu dibandingkan)
|selisih| > toleransi  -> AMOUNT_MISMATCH
bulan A != bulan B    -> PERIOD_MISMATCH
selisih = 0           -> MATCH
selain itu            -> MATCH_ROUNDING
```

## Workflow 2 (Chatbot)

AI Agent memiliki 3 tool SQL tetap: `ringkasan_terakhir`, `cari_selisih`, `cari_dokumen`. Semua query bersifat terparameter dan hanya membaca data proses rekonsiliasi **terbaru**. Memori percakapan disimpan di tabel `n8n_chat_histories`.

## Pengembangan lanjutan

- **Kunci pencocokan lain**: ubah `keyFields` di `reconcile()` (mis. hanya nomor faktur).
- **PDF/scan**: tambahkan Amazon Textract atau Bedrock vision sebelum node Parse, minta output JSON terstruktur, lalu tambahkan langkah review manual untuk keyakinan rendah.
- **Laporan Excel**: tambahkan node *Convert to File* setelah Assemble.
- **Notifikasi**: Telegram/Slack/email setelah Respond.
- **RAG**: simpan SOP/peraturan di vector store (pgvector/Qdrant) dan jadikan tool tambahan untuk Agent.
