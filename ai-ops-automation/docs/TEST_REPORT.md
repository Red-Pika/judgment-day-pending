# Laporan pengujian

Dijalankan: `python3 -W error::ResourceWarning -m unittest discover -s tests -t . -v` → **85 test, semua lulus**
(output lengkap: `evidence/test_output.txt`). Python 3.12, tanpa dependensi eksternal, tanpa jaringan.

| Berkas | Jumlah | Yang diuji |
|---|---|---|
| test_redaction.py | 11 | password/KV, JSON secret, bearer, JWT, AWS key, email, IP, URL credential, private key, kartu, objek bersarang, teks bersih tak berubah |
| test_validation.py | 10 | field wajib, severity, karakter id, panjang, tipe, bool≠angka, pemotongan log, field asing dibuang |
| test_policy.py | 7 | read-only, berisiko, denylist, chaining, baca secret, kosong, tak terparse |
| test_audit.py | 5 | rantai valid, edit & hapus terdeteksi, lanjut setelah reopen, menolak log rusak |
| test_llm.py | 8 | parsing & skema, retry, backoff eksponensial, request Anthropic (urlopen di-patch), error jaringan |
| test_approvals.py | 8 | approve/reject, parsial, langkah tak diusulkan, double decision, kedaluwarsa, approver wajib |
| test_triage.py | 10 | end-to-end: gating, **rahasia tak sampai ke LLM & audit**, prompt injection, outage, invalid, dry-run, audit |
| test_app.py | 8 | HTTP: auth, 422/400/413/404/409, alur approve, chat-sink |
| test_notify.py | 18 | Telegram (path, HTML escape, batas 4096), Slack, email via SMTP protokol sungguhan (penerima, subjek, body), multi-penerima, redaksi sebelum kirim, isolasi kegagalan channel, retry, STARTTLS+login (mock), password tak bocor di error, endpoint `/notify` (400/502, audit tanpa isi pesan) |

## Bug yang ditemukan oleh test (contoh nilai test)
Pola redaksi awal memakai `\b` sebelum kata kunci sehingga `DB_PASSWORD=...` **tidak** terredaksi
(`_` dianggap karakter kata). Terdeteksi oleh `test_password_kv` dan `test_secrets_never_reach_the_llm`,
diperbaiki dengan negative lookbehind `(?<![A-Za-z0-9])`.

## Run end-to-end (HTTP, mock LLM) — `evidence/summary.md`
Enam run: 4 alert valid, 1 invalid (422), 1 simulasi outage LLM (degraded). Audit log 32 entri valid; salinan yang
diedit pada seq 4 terdeteksi rusak. Pemindaian seluruh `evidence/` tidak menemukan satu pun rahasia mentah yang ditanam.

## Notifikasi — `evidence/notifications/summary.md`
Tiga pesan (laporan, permintaan approval, hasil) terkirim ke tiga channel tiruan; email diterima dengan RCPT `adhit.adhya01@gmail.com`; pemindaian rahasia pada semua pesan terkirim: lulus.

## Yang BELUM diuji
- Pengiriman nyata ke Telegram/Slack/Gmail (TLS, autentikasi, rate limit penyedia); workflow n8n pada instance sungguhan; panggilan live ke Claude API; beban/konkurensi tinggi; keamanan transport (TLS).
