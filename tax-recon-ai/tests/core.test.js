const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const core = require('../src/core');

const root = path.join(__dirname, '..');
const read = (...p) => fs.readFileSync(path.join(root, ...p), 'utf8');
const loadConfig = () => JSON.parse(read('config', 'mapping.json'));
const runSample = (config) => core.run(read('sample-data', 'faktur_pajak.csv'), read('sample-data', 'laporan_penjualan.csv'), config);

test('parseAmount: format Indonesia', () => {
  assert.equal(core.parseAmount('10.000.000'), 10000000);
  assert.equal(core.parseAmount('1.234,56'), 1234.56);
  assert.equal(core.parseAmount('Rp 2.500.000'), 2500000);
  assert.equal(core.parseAmount('-1.000'), -1000);
  assert.equal(core.parseAmount('(1.000)'), -1000);
  assert.equal(core.parseAmount(''), 0);
  assert.equal(core.parseAmount(1234.567), 1234.57);
});

test('parseAmount: locale en & auto', () => {
  assert.equal(core.parseAmount('10,000,000.50', 'en'), 10000000.5);
  assert.equal(core.parseAmount('1.234,56', 'auto'), 1234.56);
  assert.equal(core.parseAmount('1,234.56', 'auto'), 1234.56);
});

test('parseAmount: input tidak valid melempar error', () => {
  assert.throws(() => core.parseAmount('abc'));
  assert.throws(() => core.parseAmount('1.2,3,4'));
});

test('parseDate', () => {
  assert.equal(core.parseDate('03/09/2026'), '2026-09-03');
  assert.equal(core.parseDate('2026-9-3'), '2026-09-03');
  assert.equal(core.parseDate('31/02/2026'), null);
  assert.equal(core.parseDate('bukan tanggal'), null);
});

test('normalisasi NPWP & nomor faktur', () => {
  assert.equal(core.normalizeNpwp('01.234.567.8-901.000'), core.normalizeNpwp('012345678901000'));
  assert.equal(core.normalizeNpwp('01.234.567.8-901.000').length, 16);
  assert.equal(core.normalizeInvoiceNo('010.000-26.09000001'), '0100002609000001');
});

test('parseCsv: kutip, delimiter ; dan nomor baris', () => {
  const rows = core.parseCsv('a;b\n"x;1";2\n');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].a, 'x;1');
  assert.equal(rows[0].__row, 2);
});

test('rekonsiliasi data contoh menghasilkan status yang benar', () => {
  const out = runSample(loadConfig());
  const byNo = Object.fromEntries(out.results.map((r) => [r.invoice_no.slice(-2), r]));

  assert.equal(out.total_a, 6);
  assert.equal(out.total_b, 7);
  assert.equal(byNo['01'].status, 'MATCH');
  assert.equal(byNo['02'].status, 'AMOUNT_MISMATCH');
  assert.equal(byNo['02'].diff_dpp, 500000);
  assert.equal(byNo['02'].diff_ppn, 55000);
  assert.equal(byNo['03'].status, 'MATCH_ROUNDING');
  assert.equal(byNo['04'].status, 'ONLY_IN_A');
  assert.equal(byNo['05'].status, 'PERIOD_MISMATCH');
  assert.equal(byNo['06'].status, 'DUPLICATE_KEY');
  assert.equal(byNo['99'].status, 'ONLY_IN_B');
  assert.equal(out.discrepancy_count, 5);
  assert.match(out.run_id, /^[0-9a-f-]{36}$/);
});

test('toleransi 0 membuat selisih pembulatan menjadi mismatch', () => {
  const config = loadConfig();
  config.tolerance = 0;
  const out = runSample(config);
  assert.equal(out.results.find((r) => r.invoice_no.endsWith('03')).status, 'AMOUNT_MISMATCH');
});

test('kolom yang tidak ada memberi pesan error yang jelas', () => {
  const config = loadConfig();
  config.sourceA.columns.dpp = 'kolom_tidak_ada';
  assert.throws(
    () => core.run('nomor_faktur;dpp;ppn\n1;1;1', 'no_invoice,dpp,ppn\n1,1,1', config),
    /tidak ditemukan/,
  );
});

test('cek tarif PPN opsional menambah catatan', () => {
  const config = loadConfig();
  config.ppnRate = 0.5; // sengaja salah
  const out = runSample(config);
  assert.ok(out.results.some((r) => /tidak sesuai tarif/.test(r.notes)));
});
