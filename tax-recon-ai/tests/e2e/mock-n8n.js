/**
 * MOCK server yang meniru kontrak Chat Trigger n8n (mode webhook + Basic Auth).
 * Tujuan: menguji web/chat.html di browser sungguhan TANPA n8n/AWS.
 * Jawaban di sini berasal dari kode rekonsiliasi nyata (src/core.js) lewat template,
 * BUKAN dari LLM. Server ini bukan bukti bahwa Bedrock/n8n berfungsi.
 *
 *   node tests/e2e/mock-n8n.js [port]   (default 5679)
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const core = require('../../src/core');

const root = path.join(__dirname, '..', '..');
const PORT = Number(process.argv[2] || 5679);
const USER = 'red-pika';
const PASS = 'test-pass';
const EXPECTED = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');
const LOG = path.join(__dirname, 'mock-requests.json');

const config = JSON.parse(fs.readFileSync(path.join(root, 'config', 'mapping.json'), 'utf8'));
const data = core.run(
  fs.readFileSync(path.join(root, 'sample-data', 'faktur_pajak.csv'), 'utf8'),
  fs.readFileSync(path.join(root, 'sample-data', 'laporan_penjualan.csv'), 'utf8'),
  config,
);
const rp = (n) => (n === null ? '-' : 'Rp ' + Math.round(n).toLocaleString('id-ID'));
const mag = (r) => Math.abs(r.diff_dpp) + Math.abs(r.diff_ppn);

function answer(q) {
  const s = q.toLowerCase();
  if (s.includes('ringkasan')) {
    const c = data.summary.counts;
    return `Ringkasan terakhir: ${data.total_a} dokumen A, ${data.total_b} dokumen B. **${data.discrepancy_count}** perlu ditindaklanjuti.\n- AMOUNT_MISMATCH: ${c.AMOUNT_MISMATCH}\n- ONLY_IN_A: ${c.ONLY_IN_A}\n- ONLY_IN_B: ${c.ONLY_IN_B}\n- DUPLICATE_KEY: ${c.DUPLICATE_KEY}\n- PERIOD_MISMATCH: ${c.PERIOD_MISMATCH}`;
  }
  if (s.includes('selisih terbesar')) {
    const top = data.results.filter((r) => r.status !== 'MATCH').sort((a, b) => mag(b) - mag(a)).slice(0, 5);
    return 'Lima selisih terbesar (A - B):\n' + top.map((r, i) => `${i + 1}. \`${r.invoice_no}\` ${r.status}, DPP ${rp(r.diff_dpp)}, PPN ${rp(r.diff_ppn)}`).join('\n');
  }
  return `Anda menulis: ${q}`; // echo, dipakai untuk uji escape HTML
}

http.createServer((req, res) => {
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  };
  if (req.method === 'OPTIONS') { res.writeHead(204, cors); return res.end(); }
  if (req.url !== '/webhook/test/chat' || req.method !== 'POST') { res.writeHead(404, cors); return res.end(); }
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', () => {
    const entry = { time: new Date().toISOString(), authOk: req.headers.authorization === EXPECTED, contentType: req.headers['content-type'], body: null };
    try { entry.body = JSON.parse(body); } catch (e) { /* biarkan null */ }
    const log = fs.existsSync(LOG) ? JSON.parse(fs.readFileSync(LOG, 'utf8')) : [];
    log.push(entry);
    fs.writeFileSync(LOG, JSON.stringify(log, null, 2));
    if (!entry.authOk) { res.writeHead(401, { ...cors, 'Content-Type': 'application/json' }); return res.end('{"message":"Authorization problem"}'); }
    const reply = answer(String((entry.body || {}).chatInput || ''));
    res.writeHead(200, { ...cors, 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ output: reply }));
  });
}).listen(PORT, '127.0.0.1', () => console.log(`mock n8n chat di http://127.0.0.1:${PORT}/webhook/test/chat`));
