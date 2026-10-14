/**
 * Memeriksa file workflow n8n yang dihasilkan: struktur, koneksi, konfigurasi keamanan,
 * dan menjalankan kode node Code dengan mock $input / this.helpers.
 * (Tidak menggantikan uji import di n8n sungguhan.)
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '..');
const load = (f) => JSON.parse(fs.readFileSync(path.join(root, 'n8n', f), 'utf8'));
const wf1 = load('workflow-1-rekonsiliasi.json');
const wf2 = load('workflow-2-chatbot.json');
const byName = (wf, n) => wf.nodes.find((x) => x.name === n);

for (const [label, wf] of [['workflow 1', wf1], ['workflow 2', wf2]]) {
  test(`${label}: id & nama node unik, semua koneksi valid`, () => {
    assert.equal(new Set(wf.nodes.map((n) => n.id)).size, wf.nodes.length);
    assert.equal(new Set(wf.nodes.map((n) => n.name)).size, wf.nodes.length);
    const names = new Set(wf.nodes.map((n) => n.name));
    for (const [src, conns] of Object.entries(wf.connections)) {
      assert.ok(names.has(src), `sumber tidak ada: ${src}`);
      for (const outs of Object.values(conns)) for (const arr of outs) for (const c of arr) assert.ok(names.has(c.node), `target tidak ada: ${c.node}`);
    }
  });
}

test('workflow 1: webhook upload wajib Header Auth', () => {
  const w = byName(wf1, 'Webhook Upload');
  assert.equal(w.parameters.authentication, 'headerAuth');
  assert.ok(w.credentials.httpHeaderAuth);
});

test('workflow 2: chat trigger publik tetapi wajib Basic Auth', () => {
  const t = byName(wf2, 'Chat Trigger');
  assert.equal(t.parameters.public, true);
  assert.equal(t.parameters.authentication, 'basicAuth');
  assert.ok(t.credentials.httpBasicAuth);
});

test('workflow 2: agent terhubung ke model, memori, dan 3 tool', () => {
  const into = (type) => Object.values(wf2.connections).flatMap((c) => (c[type] || []).flat()).filter((x) => x.node === 'AI Agent');
  assert.equal(into('ai_languageModel').length, 1);
  assert.equal(into('ai_memory').length, 1);
  assert.equal(into('ai_tool').length, 3);
});

test('workflow 2: tool SQL terparameter, tanpa interpolasi, jumlah $n = jumlah nilai', () => {
  for (const n of wf2.nodes.filter((x) => x.type === 'n8n-nodes-base.postgresTool')) {
    const q = n.parameters.query;
    assert.ok(!q.includes('{{'), `${n.name}: ada interpolasi di query`);
    const placeholders = new Set(q.match(/\$\d/g) || []).size;
    const repl = n.parameters.options.queryReplacement;
    const values = repl ? (repl.match(/\$fromAI\(/g) || []).length : 0;
    assert.equal(placeholders, values, `${n.name}: ${placeholders} placeholder vs ${values} nilai`);
    assert.ok(!/\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b/i.test(q), `${n.name}: query bukan read-only`);
  }
});

test('kode node Code workflow 1 berjalan end-to-end dengan data contoh', async () => {
  const A = fs.readFileSync(path.join(root, 'sample-data', 'faktur_pajak.csv'));
  const B = fs.readFileSync(path.join(root, 'sample-data', 'laporan_penjualan.csv'));
  const code = (n) => byName(wf1, n).parameters.jsCode;
  const run = (name, ctx, self) => vm.runInContext(`(async function(){${code(name)}})`, vm.createContext({ console, ...ctx })).call(self);

  const helpers = { getBinaryDataBuffer: async (_i, k) => (k === 'fileA' ? A : B) };
  const input = { json: { body: { tolerance: '10' } }, binary: { fileA: {}, fileB: {} } };
  const base = (await run('Parse and Reconcile', { $input: { first: () => input } }, { helpers }))[0].json;
  assert.equal(base.discrepancy_count, 5);
  assert.equal(base.results.length, 7);

  const prompt = (await run('Build Prompt', { $input: { first: () => ({ json: base }) } }))[0].json;
  assert.ok(prompt.prompt.includes('010.000-26.09000099'));

  const ctx = { $input: { first: () => ({ json: { text: 'penjelasan' } }) }, $: () => ({ first: () => ({ json: base }) }) };
  const asm = (await run('Assemble', ctx))[0].json;
  assert.equal(asm.ai_explanation, 'penjelasan');
  assert.ok(asm.top_discrepancies.every((r) => !('run_id' in r)));

  const prep = (await run('Prep Run Row', { $input: { first: () => ({ json: asm }) } }))[0].json;
  assert.equal(typeof prep.summary, 'string');

  const sql = fs.readFileSync(path.join(root, 'db', 'init.sql'), 'utf8');
  for (const col of Object.keys(base.results[0])) assert.match(sql, new RegExp(`\\b${col}\\s`), `kolom ${col} tidak ada di db/init.sql`);
});

test('Assemble: tanpa selisih -> teks default; AI gagal -> pesan fallback', async () => {
  const code = byName(wf1, 'Assemble').parameters.jsCode;
  const run = (base, input) => vm.runInContext(`(async function(){${code}})`, vm.createContext({ $input: { first: () => ({ json: input }) }, $: () => ({ first: () => ({ json: base }) }) }))();
  const none = (await run({ discrepancy_count: 0, results: [], summary: {}, warnings: [] }, {}))[0].json;
  assert.match(none.ai_explanation, /Tidak ada selisih/);
  const failed = (await run({ discrepancy_count: 2, results: [], summary: {}, warnings: [] }, {}))[0].json;
  assert.match(failed.ai_explanation, /tidak tersedia/);
});
