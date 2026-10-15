# Arsitektur & alur data

## Komponen
| Komponen | Tanggung jawab | Tidak boleh |
|---|---|---|
| **n8n** | Menerima webhook, retry, cabang error, notifikasi chat, menunggu approval (Wait node) | Memegang logika keamanan |
| **opsguard** (service) | Validasi, redaksi, panggil LLM, klasifikasi risiko, approval, audit | Mengeksekusi perintah (dry-run saja) |
| **LLM (Claude)** | Meringkas log, hipotesis penyebab, usulan langkah (JSON) | Dipercaya: outputnya diperlakukan sebagai input tak tepercaya |
| **Notifier** (`/notify`) | Fan-out ke Telegram / Slack / Email, redaksi ulang, isolasi kegagalan per channel | Menyimpan isi pesan di audit log |
| **Chat/Email** | Menampilkan laporan & meminta keputusan manusia | — |

Logika keamanan sengaja ada di service (bisa di-unit-test), bukan di node n8n.

## Alur data
```mermaid
sequenceDiagram
  participant M as Monitoring (simulator)
  participant N as n8n
  participant S as opsguard
  participant L as LLM
  participant H as Engineer (chat)
  M->>N: POST /webhook/ops-alert
  N->>S: POST /triage (X-Service-Token)
  S->>S: validate -> audit(alert_received)
  S->>S: redact (secrets/PII) -> audit(input_redacted)
  S->>L: prompt (data ber-tag, sudah diredaksi)
  L-->>S: JSON {summary, cause, steps}
  S->>S: parse ketat -> redact output -> classify tiap command
  S->>S: blocked/low/high -> buat approval ticket -> audit
  S-->>N: report + markdown
  N->>H: laporan; jika requires_approval: minta keputusan
  H->>N: resume URL {decision, approver}  (atau timeout 15 mnt = rejected)
  N->>S: POST /approvals/{id}/decision
  S->>S: dry-run langkah yang disetujui -> audit
  S-->>N: hasil -> N->>H: outcome
```

## Data apa yang pergi ke mana
| Data | Ke LLM | Ke audit log | Ke chat |
|---|---|---|---|
| Alert id, severity, service, summary | ya (setelah redaksi) | ya | ya |
| Baris log | ya, **setelah redaksi**, maks 200 baris terakhir | **tidak** (hanya jumlah baris) | tidak |
| Rahasia/PII (password, token, email, IP, kartu, private key) | **tidak** | **tidak** | **tidak** |
| Jumlah redaksi per jenis | — | ya | ringkas |

## Model ancaman singkat
| Ancaman | Mitigasi | Test |
|---|---|---|
| Rahasia di log bocor ke penyedia LLM | Redaksi sebelum prompt | `test_secrets_never_reach_the_llm` |
| Prompt injection lewat log | Data di-tag "untrusted" **dan** (kontrol sebenarnya) policy pada output | `test_prompt_injection_cannot_cause_dangerous_action` |
| LLM mengusulkan perintah destruktif | Denylist → blocked; selain allowlist read-only → perlu approval | `test_policy.py` |
| Label risiko dari LLM dipalsukan | Label LLM diabaikan; policy yang menilai | desain |
| Chaining `a; b` menyelundupkan perintah | Metachar → minimal "high" | `test_chaining_hides_nothing` |
| Approval dipakai ulang / kedaluwarsa | Sekali pakai, TTL 15 mnt, 409/410 | `test_approvals.py` |
| Log audit diubah belakangan | Hash chain, startup menolak log rusak | `test_audit.py` |
| Webhook/service dipanggil tanpa izin | Shared secret (constant-time compare) | `test_requires_token` |
| Payload raksasa | Batas 256 KB → 413; batas baris/field | `test_oversized_body_413` |
