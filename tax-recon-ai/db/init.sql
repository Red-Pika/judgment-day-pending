-- Dijalankan otomatis oleh container Postgres saat volume masih kosong.
-- Database "n8n" dipakai n8n sendiri; "taxrecon" menyimpan hasil rekonsiliasi.
CREATE DATABASE taxrecon;
\c taxrecon

CREATE TABLE IF NOT EXISTS recon_runs (
  run_id          UUID PRIMARY KEY,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  tolerance       NUMERIC(20,2),
  total_a         INTEGER,
  total_b         INTEGER,
  summary         JSONB,
  ai_explanation  TEXT
);

CREATE TABLE IF NOT EXISTS recon_results (
  id          BIGSERIAL PRIMARY KEY,
  run_id      UUID NOT NULL,
  status      TEXT NOT NULL CHECK (status IN (
                'MATCH','MATCH_ROUNDING','AMOUNT_MISMATCH','PERIOD_MISMATCH',
                'ONLY_IN_A','ONLY_IN_B','DUPLICATE_KEY')),
  invoice_no  TEXT,
  npwp        TEXT,
  date_a      DATE,
  date_b      DATE,
  dpp_a       NUMERIC(20,2),
  dpp_b       NUMERIC(20,2),
  diff_dpp    NUMERIC(20,2),
  ppn_a       NUMERIC(20,2),
  ppn_b       NUMERIC(20,2),
  diff_ppn    NUMERIC(20,2),
  notes       TEXT,
  row_a       INTEGER,
  row_b       INTEGER,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recon_results_run    ON recon_results (run_id);
CREATE INDEX IF NOT EXISTS idx_recon_results_status ON recon_results (status);
CREATE INDEX IF NOT EXISTS idx_recon_results_inv    ON recon_results (invoice_no);

-- (Disarankan) user read-only untuk tool chatbot. Ganti password-nya!
-- CREATE ROLE chatbot_ro LOGIN PASSWORD 'GANTI_PASSWORD';
-- GRANT CONNECT ON DATABASE taxrecon TO chatbot_ro;
-- GRANT SELECT ON recon_runs, recon_results TO chatbot_ro;
