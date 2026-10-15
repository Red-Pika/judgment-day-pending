# Penanganan kegagalan & biaya

## Matriks kegagalan
| Kegagalan | Perilaku | Bukti |
|---|---|---|
| Alert tidak valid | 422, tidak ada panggilan LLM, tercatat `alert_rejected` | `evidence/reports/invalid_alert.json` |
| LLM timeout/5xx/jaringan | Retry eksponensial (default 2x: 0.5s, 1s) → **mode degraded**: laporan tetap terkirim, tanpa langkah, ditandai manual | `evidence/reports/llm_outage.md` |
| LLM mengembalikan JSON/skema salah | Diperlakukan seperti kegagalan → retry → degraded | `test_llm.py` |
| LLM mengusulkan perintah berbahaya | Langkah di-block, tercatat `step_blocked`, tidak pernah masuk approval | `evidence/reports/prompt_injection.md` |
| Tidak ada yang menyetujui | Wait node timeout 15 mnt → keputusan `rejected` oleh `system-timeout`; service juga menolak setelah TTL (410) | `test_expiry` |
| Service tidak bisa dijangkau n8n | Retry node (2x) → cabang error → pesan "Triage failed - handle manually" | `workflow.json` |
| Audit log rusak | Service menolak start (`AuditTamperError`) | `test_refuses_to_open_tampered_log` |
| Dua orang menyetujui bersamaan | Yang kedua 409 | `approval_decisions.json` |

Prinsip: **gagal ke arah aman** — saat ragu, manusia yang memutuskan dan tidak ada aksi otomatis.

## Biaya
Biaya per alert = `(input_tokens × harga_in + output_tokens × harga_out) / 1.000.000`. Token nyata dicatat per alert
di audit log (`llm_call_ok`) dan di field `usage` / `estimated_cost_usd` pada laporan.

Contoh perhitungan memakai **harga ilustratif** USD 1 / 5 per juta token (bukan harga resmi — isi
`PRICE_IN_PER_MTOK` / `PRICE_OUT_PER_MTOK` dari halaman harga Anthropic):

| Skenario | Token in / out (estimasi mock) | Biaya per alert | Per 1.000 alert |
|---|---|---|---|
| oom_checkout (3 baris log) | 356 / 156 | ≈ $0.0011 | ≈ $1.14 |
| db_timeout | 288 / 138 | ≈ $0.0010 | ≈ $0.98 |

Angka token di atas adalah estimasi (`panjang_teks/4`) dari mock; ganti dengan `usage` nyata setelah run live.
Alert dengan 200 baris log akan jauh lebih besar — itulah kontrol biaya utama.

Pengendali biaya yang sudah ada: log dipotong 200 baris terakhir & 2.000 karakter/baris, `max_tokens` 1.000,
maksimum 6 langkah, tidak ada panggilan LLM untuk alert invalid, model kecil sebagai default.
Belum ada (ide lanjutan): dedup alert berulang, rate limit per service, anggaran harian dengan circuit breaker.
