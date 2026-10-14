#!/usr/bin/env node
/**
 * Membuat file workflow n8n (JSON) dari satu sumber kebenaran:
 *   - src/core.js              -> isi node Code (logika rekonsiliasi)
 *   - config/mapping.json      -> mapping kolom & toleransi default
 *   - prompts/*.md             -> prompt LLM
 *
 * Jalankan setiap kali salah satu file di atas berubah:
 *   npm run build:n8n
 * Lalu import ulang file di folder n8n/ ke n8n.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const root = path.join(__dirname, '..');
const read = (...p) => fs.readFileSync(path.join(root, ...p), 'utf8');

const CORE = read('src', 'core.js');
const MAPPING = JSON.stringify(JSON.parse(read('config', 'mapping.json')), null, 2);
const EXPLAIN_PROMPT = read('prompts', 'explain_discrepancy.md').trim();
const CHATBOT_PROMPT = read('prompts', 'chatbot_system.md').trim();

const id = (name) => {
  const h = crypto.createHash('sha1').update(name).digest('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
};
const PG_CRED = { postgres: { id: 'GANTI_DENGAN_CREDENTIAL_ANDA', name: 'Postgres - taxrecon' } };
const AWS_CRED = { aws: { id: 'GANTI_DENGAN_CREDENTIAL_ANDA', name: 'AWS - Bedrock' } };
const HEADER_CRED = { httpHeaderAuth: { id: 'GANTI_DENGAN_CREDENTIAL_ANDA', name: 'Header Auth - Upload' } };
const BASIC_CRED = { httpBasicAuth: { id: 'GANTI_DENGAN_CREDENTIAL_ANDA', name: 'Basic Auth - Chatbot' } };
// Batasi ke domain web chat Anda saat build, mis: CHAT_ALLOWED_ORIGINS=https://user.github.io npm run build:n8n
const CHAT_ALLOWED_ORIGINS = process.env.CHAT_ALLOWED_ORIGINS || '*';

function node(name, type, typeVersion, position, parameters, extra = {}) {
  return { parameters, id: id(name), name, type, typeVersion, position, ...extra };
}
const link = (to, type = 'main') => ({ node: to, type, index: 0 });

// ======================================================================
// WORKFLOW 1: Rekonsiliasi (Webhook -> hitung -> simpan -> penjelasan AI)
// ======================================================================
const PARSE_GLUE = `
// ---- Bagian khusus n8n (glue) ----
const input = $input.first();
const body = (input.json && input.json.body) || {};
const binary = input.binary || {};
if (!binary.fileA || !binary.fileB) {
  throw new Error('Kirim multipart/form-data dengan 2 file CSV: "fileA" dan "fileB".');
}
const bufA = await this.helpers.getBinaryDataBuffer(0, 'fileA');
const bufB = await this.helpers.getBinaryDataBuffer(0, 'fileB');

const config = { ...DEFAULT_CONFIG };
if (body.tolerance !== undefined && body.tolerance !== '') config.tolerance = Number(body.tolerance);
if (body.ppnRate !== undefined && body.ppnRate !== '') config.ppnRate = Number(body.ppnRate);
if (body.locale) config.locale = String(body.locale);

return [{ json: TaxRecon.run(bufA.toString('utf8'), bufB.toString('utf8'), config) }];
`;

const parseCode = `${CORE}\n\nconst DEFAULT_CONFIG = ${MAPPING};\n${PARSE_GLUE}`;

const buildPromptCode = `// Siapkan data selisih untuk dijelaskan AI. Angka sudah final, AI hanya menjelaskan.
const d = $input.first().json;
const MAX_ROWS = 50;
const bad = d.results.filter((r) => r.status !== 'MATCH' && r.status !== 'MATCH_ROUNDING');
bad.sort((x, y) => (Math.abs(y.diff_dpp) + Math.abs(y.diff_ppn)) - (Math.abs(x.diff_dpp) + Math.abs(x.diff_ppn)));
const rows = bad.slice(0, MAX_ROWS).map((r) => ({
  nomor: r.invoice_no, npwp: r.npwp, status: r.status,
  dpp_a: r.dpp_a, dpp_b: r.dpp_b, diff_dpp: r.diff_dpp,
  ppn_a: r.ppn_a, ppn_b: r.ppn_b, diff_ppn: r.diff_ppn,
  tanggal_a: r.date_a, tanggal_b: r.date_b, catatan: r.notes,
}));
const prompt =
  'Ringkasan: ' + JSON.stringify(d.summary) + '\\n\\n' +
  'Daftar selisih (' + rows.length + ' dari ' + bad.length + ' ditampilkan, urut selisih terbesar):\\n' +
  JSON.stringify(rows, null, 1);
return [{ json: { discrepancy_count: d.discrepancy_count, prompt } }];`;

const assembleCode = `// Gabungkan hasil hitung (deterministik) + penjelasan AI.
const base = $('Parse and Reconcile').first().json;
const aiText = $input.first().json.text;
const explanation = base.discrepancy_count === 0
  ? 'Tidak ada selisih yang perlu dijelaskan.'
  : (aiText || 'Penjelasan AI tidak tersedia (cek koneksi Bedrock). Hasil perhitungan tetap valid.');
const top = base.results
  .filter((r) => r.status !== 'MATCH' && r.status !== 'MATCH_ROUNDING')
  .sort((x, y) => (Math.abs(y.diff_dpp) + Math.abs(y.diff_ppn)) - (Math.abs(x.diff_dpp) + Math.abs(x.diff_ppn)))
  .slice(0, 20)
  .map(({ run_id, ...rest }) => rest);
return [{ json: {
  run_id: base.run_id,
  tolerance: base.tolerance,
  total_a: base.total_a,
  total_b: base.total_b,
  summary: base.summary,
  warnings: base.warnings,
  discrepancy_count: base.discrepancy_count,
  top_discrepancies: top,
  ai_explanation: explanation,
} }];`;

const prepRunCode = `// summary harus berupa string JSON untuk kolom jsonb.
const j = $input.first().json;
return [{ json: {
  run_id: j.run_id, tolerance: j.tolerance, total_a: j.total_a, total_b: j.total_b,
  summary: JSON.stringify(j.summary), ai_explanation: j.ai_explanation,
} }];`;

const wf1Nodes = [
  node('Webhook Upload', 'n8n-nodes-base.webhook', 2, [0, 200],
    { httpMethod: 'POST', path: 'tax-recon', authentication: 'headerAuth', responseMode: 'responseNode', options: {} },
    { webhookId: id('webhook-tax-recon'), credentials: HEADER_CRED }),
  node('Parse and Reconcile', 'n8n-nodes-base.code', 2, [260, 200], { jsCode: parseCode }),
  node('Split Results', 'n8n-nodes-base.splitOut', 1, [540, 40], { fieldToSplitOut: 'results', options: {} }),
  node('Save Results', 'n8n-nodes-base.postgres', 2.5, [800, 40], {
    operation: 'insert',
    schema: { __rl: true, mode: 'list', value: 'public' },
    table: { __rl: true, mode: 'name', value: 'recon_results' },
    columns: { mappingMode: 'autoMapInputData', value: null, matchingColumns: [], schema: [] },
    options: {},
  }, { credentials: PG_CRED }),
  node('Build Prompt', 'n8n-nodes-base.code', 2, [540, 360], { jsCode: buildPromptCode }),
  node('Ada Selisih?', 'n8n-nodes-base.if', 2.2, [800, 360], {
    conditions: {
      options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
      conditions: [{
        id: id('cond-ada-selisih'),
        leftValue: '={{ $json.discrepancy_count }}',
        rightValue: 0,
        operator: { type: 'number', operation: 'gt' },
      }],
      combinator: 'and',
    },
    options: {},
  }),
  node('Explain Discrepancies', '@n8n/n8n-nodes-langchain.chainLlm', 1.5, [1060, 300], {
    promptType: 'define',
    text: '={{ $json.prompt }}',
    messages: { messageValues: [{ message: EXPLAIN_PROMPT }] },
  }, { onError: 'continueRegularOutput' }),
  node('Bedrock Chat Model', '@n8n/n8n-nodes-langchain.lmChatAwsBedrock', 1, [1100, 520],
    { options: { temperature: 0.1, maxTokensToSample: 2000 } }, { credentials: AWS_CRED }),
  node('Assemble', 'n8n-nodes-base.code', 2, [1340, 360], { jsCode: assembleCode }),
  node('Respond', 'n8n-nodes-base.respondToWebhook', 1.1, [1600, 300],
    { respondWith: 'json', responseBody: '={{ $json }}', options: {} }),
  node('Prep Run Row', 'n8n-nodes-base.code', 2, [1600, 460], { jsCode: prepRunCode }),
  node('Save Run', 'n8n-nodes-base.postgres', 2.5, [1860, 460], {
    operation: 'insert',
    schema: { __rl: true, mode: 'list', value: 'public' },
    table: { __rl: true, mode: 'name', value: 'recon_runs' },
    columns: { mappingMode: 'autoMapInputData', value: null, matchingColumns: [], schema: [] },
    options: {},
  }, { credentials: PG_CRED }),
  node('Catatan', 'n8n-nodes-base.stickyNote', 1, [-20, -160], {
    width: 760, height: 300,
    content: [
      '## Tax Recon - Workflow 1: Rekonsiliasi',
      '1. Buat credential **Postgres** (database `taxrecon`) dan **AWS** (akses Bedrock), lalu pilih di node Save Results, Save Run, dan Bedrock Chat Model.',
      '2. Di node **Bedrock Chat Model**, pilih model yang sudah Anda aktifkan aksesnya di konsol Bedrock.',
      '3. Buat credential **Header Auth** (mis. Name `X-API-Key`, Value = kunci acak) di node Webhook Upload. Kirim 2 file CSV: `curl -H "X-API-Key: <kunci>" -F fileA=@a.csv -F fileB=@b.csv -F tolerance=10 <URL webhook>`',
      '4. **Angka dihitung node "Parse and Reconcile" (kode), bukan oleh AI.** AI hanya menjelaskan.',
      '5. Jangan edit kode di node Parse; ubah `src/core.js` lalu jalankan `npm run build:n8n`.',
    ].join('\n'),
  }),
];

const wf1 = {
  name: 'Tax Recon - 1 Rekonsiliasi',
  nodes: wf1Nodes,
  connections: {
    'Webhook Upload': { main: [[link('Parse and Reconcile')]] },
    'Parse and Reconcile': { main: [[link('Split Results'), link('Build Prompt')]] },
    'Split Results': { main: [[link('Save Results')]] },
    'Build Prompt': { main: [[link('Ada Selisih?')]] },
    'Ada Selisih?': { main: [[link('Explain Discrepancies')], [link('Assemble')]] },
    'Explain Discrepancies': { main: [[link('Assemble')]] },
    'Bedrock Chat Model': { ai_languageModel: [[link('Explain Discrepancies', 'ai_languageModel')]] },
    Assemble: { main: [[link('Respond'), link('Prep Run Row')]] },
    'Prep Run Row': { main: [[link('Save Run')]] },
  },
  settings: { executionOrder: 'v1' },
  pinData: {},
};

// ======================================================================
// WORKFLOW 2: Chatbot (Chat Trigger -> AI Agent + tools SQL terparameter)
// ======================================================================
const LATEST = '(SELECT run_id FROM recon_runs ORDER BY created_at DESC LIMIT 1)';

const sqlSelisih = `SELECT invoice_no, npwp, status, dpp_a, dpp_b, diff_dpp, ppn_a, ppn_b, diff_ppn, notes
FROM recon_results
WHERE run_id = ${LATEST}
  AND status <> 'MATCH'
  AND ($1::text = 'SEMUA' OR status = $1::text)
ORDER BY ABS(COALESCE(diff_dpp,0)) + ABS(COALESCE(diff_ppn,0)) DESC
LIMIT $2::int`;

const sqlDokumen = `SELECT invoice_no, npwp, status, date_a, date_b, dpp_a, dpp_b, diff_dpp, ppn_a, ppn_b, diff_ppn, notes
FROM recon_results
WHERE run_id = ${LATEST}
  AND invoice_no ILIKE '%' || $1::text || '%'
ORDER BY invoice_no
LIMIT 20`;

const sqlRingkasan = `SELECT run_id, created_at, tolerance, total_a, total_b, summary, ai_explanation
FROM recon_runs
ORDER BY created_at DESC
LIMIT 1`;

const pgTool = (name, y, description, query, replacement) => node(name, 'n8n-nodes-base.postgresTool', 2.5, [600, y], {
  descriptionType: 'manual',
  toolDescription: description,
  operation: 'executeQuery',
  query,
  options: replacement ? { queryReplacement: replacement } : {},
}, { credentials: PG_CRED });

const wf2Nodes = [
  node('Chat Trigger', '@n8n/n8n-nodes-langchain.chatTrigger', 1.1, [0, 200],
    { public: true, mode: 'webhook', authentication: 'basicAuth', options: { allowedOrigins: CHAT_ALLOWED_ORIGINS } },
    { webhookId: id('chat-tax-recon'), credentials: BASIC_CRED }),
  node('AI Agent', '@n8n/n8n-nodes-langchain.agent', 1.7, [300, 200],
    { options: { systemMessage: CHATBOT_PROMPT, maxIterations: 6 } }),
  node('Bedrock Chat Model', '@n8n/n8n-nodes-langchain.lmChatAwsBedrock', 1, [100, 420],
    { options: { temperature: 0.1, maxTokensToSample: 2000 } }, { credentials: AWS_CRED }),
  node('Postgres Chat Memory', '@n8n/n8n-nodes-langchain.memoryPostgresChat', 1.3, [330, 420],
    { tableName: 'n8n_chat_histories', contextWindowLength: 10 }, { credentials: PG_CRED }),
  pgTool('ringkasan_terakhir', 420,
    'Ringkasan hasil rekonsiliasi terbaru: jumlah dokumen, jumlah per status, total DPP/PPN, dan penjelasan AI. Tanpa parameter.',
    sqlRingkasan),
  pgTool('cari_selisih', 560,
    'Daftar dokumen yang bermasalah (bukan MATCH) pada rekonsiliasi terbaru, urut selisih terbesar. diff = A - B. Parameter: status (SEMUA, MATCH_ROUNDING, AMOUNT_MISMATCH, PERIOD_MISMATCH, ONLY_IN_A, ONLY_IN_B, DUPLICATE_KEY) dan jumlah baris.',
    sqlSelisih,
    "={{ [ $fromAI('status', 'Filter status. Salah satu: SEMUA, MATCH_ROUNDING, AMOUNT_MISMATCH, PERIOD_MISMATCH, ONLY_IN_A, ONLY_IN_B, DUPLICATE_KEY. Default SEMUA', 'string'), $fromAI('jumlah_baris', 'Jumlah baris maksimal, default 10, maksimal 50', 'number') ] }}"),
  pgTool('cari_dokumen', 700,
    'Cari dokumen pada rekonsiliasi terbaru berdasarkan sebagian nomor faktur/invoice. Parameter: potongan_nomor.',
    sqlDokumen,
    "={{ [ $fromAI('potongan_nomor', 'Sebagian nomor faktur atau invoice yang dicari', 'string') ] }}"),
  node('Catatan', 'n8n-nodes-base.stickyNote', 1, [-20, -160], {
    width: 700, height: 300,
    content: [
      '## Tax Recon - Workflow 2: Chatbot',
      '1. Pilih credential Postgres & AWS di node Chat Memory, 3 tool SQL, dan Bedrock Chat Model; pilih model Bedrock Anda.',
      '2. Jalankan Workflow 1 minimal sekali agar tabel berisi data. Buat credential **Basic Auth** (username/password login chat) di node Chat Trigger.',
      '3. Aktifkan workflow, salin **Production URL** Chat Trigger, lalu pakai di `web/chat.html`.',
      '4. Tool memakai **query terparameter yang tetap** (bukan SQL buatan AI) sehingga aman dari SQL injection.',
      '5. Untuk 3 tool SQL, disarankan credential Postgres **read-only** (lihat db/init.sql). Chat Memory butuh credential yang bisa menulis.',
    ].join('\n'),
  }),
];

const wf2 = {
  name: 'Tax Recon - 2 Chatbot',
  nodes: wf2Nodes,
  connections: {
    'Chat Trigger': { main: [[link('AI Agent')]] },
    'Bedrock Chat Model': { ai_languageModel: [[link('AI Agent', 'ai_languageModel')]] },
    'Postgres Chat Memory': { ai_memory: [[link('AI Agent', 'ai_memory')]] },
    ringkasan_terakhir: { ai_tool: [[link('AI Agent', 'ai_tool')]] },
    cari_selisih: { ai_tool: [[link('AI Agent', 'ai_tool')]] },
    cari_dokumen: { ai_tool: [[link('AI Agent', 'ai_tool')]] },
  },
  settings: { executionOrder: 'v1' },
  pinData: {},
};

// ----------------------------------------------------------------------
const outDir = path.join(root, 'n8n');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'workflow-1-rekonsiliasi.json'), JSON.stringify(wf1, null, 2) + '\n');
fs.writeFileSync(path.join(outDir, 'workflow-2-chatbot.json'), JSON.stringify(wf2, null, 2) + '\n');
console.log('OK: n8n/workflow-1-rekonsiliasi.json & n8n/workflow-2-chatbot.json');
