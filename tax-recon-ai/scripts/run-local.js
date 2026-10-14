#!/usr/bin/env node
/**
 * Jalankan rekonsiliasi dari terminal (tanpa n8n / AWS) untuk uji coba.
 *
 *   node scripts/run-local.js
 *   node scripts/run-local.js --a data/a.csv --b data/b.csv --tolerance 10 --out output
 */
const fs = require('fs');
const path = require('path');
const core = require('../src/core');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];

const root = path.join(__dirname, '..');
const fileA = args.a || path.join(root, 'sample-data', 'faktur_pajak.csv');
const fileB = args.b || path.join(root, 'sample-data', 'laporan_penjualan.csv');
const configPath = args.mapping || path.join(root, 'config', 'mapping.json');
const outDir = args.out || path.join(root, 'output');

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
if (args.tolerance !== undefined) config.tolerance = Number(args.tolerance);
if (args.ppnRate !== undefined) config.ppnRate = Number(args.ppnRate);

const out = core.run(fs.readFileSync(fileA, 'utf8'), fs.readFileSync(fileB, 'utf8'), config);

fs.mkdirSync(outDir, { recursive: true });
const columns = ['status', 'invoice_no', 'npwp', 'date_a', 'date_b', 'dpp_a', 'dpp_b', 'diff_dpp', 'ppn_a', 'ppn_b', 'diff_ppn', 'notes', 'row_a', 'row_b'];
fs.writeFileSync(path.join(outDir, 'hasil_rekonsiliasi.csv'), core.toCsv(out.results, columns));
fs.writeFileSync(path.join(outDir, 'ringkasan.json'), JSON.stringify({ ...out, results: undefined }, null, 2));

console.log(`Dokumen A: ${out.total_a} | Dokumen B: ${out.total_b} | Toleransi: Rp ${out.tolerance}`);
console.log(`Cocok: ${out.summary.matched_pct}% dari ${out.summary.total_keys} kunci\n`);
console.table(out.summary.counts);
console.log(`Selisih total DPP (A-B): ${out.summary.net_diff_dpp}`);
console.log(`Selisih total PPN (A-B): ${out.summary.net_diff_ppn}`);
if (out.warnings.length) { console.log('\nPeringatan:'); out.warnings.forEach((w) => console.log(` - ${w.source} baris ${w.row}: ${w.message}`)); }
console.log(`\nHasil disimpan di: ${outDir}`);
