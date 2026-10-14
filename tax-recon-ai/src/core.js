/**
 * Tax Recon AI - core logic (deterministik, TANPA LLM).
 *
 * File ini sengaja ditulis tanpa dependency dan tanpa require(), sehingga:
 *   1. bisa dipakai di Node.js (CLI + unit test), dan
 *   2. bisa di-embed langsung ke node "Code" n8n (lihat scripts/build-n8n.js).
 *
 * Semua perhitungan angka dilakukan di sini. LLM hanya dipakai untuk
 * MENJELASKAN hasil, tidak pernah untuk menghitung atau membandingkan.
 */
const TaxRecon = (() => {
  'use strict';

  const STATUSES = [
    'MATCH',
    'MATCH_ROUNDING',
    'AMOUNT_MISMATCH',
    'PERIOD_MISMATCH',
    'ONLY_IN_A',
    'ONLY_IN_B',
    'DUPLICATE_KEY',
  ];

  const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;
  const pad2 = (n) => String(n).padStart(2, '0');

  // ---------------------------------------------------------------- CSV
  function detectDelimiter(headerLine) {
    const counts = { ',': 0, ';': 0, '\t': 0 };
    let inQuote = false;
    for (const ch of headerLine) {
      if (ch === '"') inQuote = !inQuote;
      else if (!inQuote && Object.prototype.hasOwnProperty.call(counts, ch)) counts[ch]++;
    }
    return Object.entries(counts).sort((x, y) => y[1] - x[1])[0][0];
  }

  /** Parser CSV kecil: mendukung kutip ganda, delimiter , ; dan tab. Baris pertama = header. */
  function parseCsv(text) {
    text = String(text).replace(/^\uFEFF/, '');
    const delim = detectDelimiter(text.split(/\r?\n/, 1)[0] || '');
    const rows = [];
    let row = [];
    let field = '';
    let inQuote = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inQuote) {
        if (ch === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else inQuote = false;
        } else field += ch;
      } else if (ch === '"') {
        inQuote = true;
      } else if (ch === delim) {
        row.push(field); field = '';
      } else if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = '';
        rows.push(row); row = [];
      } else field += ch;
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }

    const nonEmpty = rows.filter((r) => r.some((c) => String(c).trim() !== ''));
    if (!nonEmpty.length) return [];
    const headers = nonEmpty[0].map((h) => String(h).trim());
    return nonEmpty.slice(1).map((r, idx) => {
      const o = { __row: idx + 2 }; // nomor baris di file asli (header = baris 1)
      headers.forEach((h, i) => { o[h] = r[i] !== undefined ? String(r[i]).trim() : ''; });
      return o;
    });
  }

  function toCsv(rows, columns) {
    const esc = (v) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return [columns.join(',')]
      .concat(rows.map((r) => columns.map((c) => esc(r[c])).join(',')))
      .join('\n');
  }

  // -------------------------------------------------------- Normalisasi
  function autoNormalize(s) {
    const lastDot = s.lastIndexOf('.');
    const lastComma = s.lastIndexOf(',');
    if (lastDot >= 0 && lastComma >= 0) {
      const dec = lastDot > lastComma ? '.' : ',';
      const thou = dec === '.' ? ',' : '.';
      return s.split(thou).join('').replace(dec, '.');
    }
    const sep = lastDot >= 0 ? '.' : lastComma >= 0 ? ',' : null;
    if (!sep) return s;
    const count = s.split(sep).length - 1;
    const after = s.length - s.lastIndexOf(sep) - 1;
    // Ambigu ("1.234"): 3 digit di belakang separator dianggap pemisah ribuan.
    if (count > 1 || after === 3) return s.split(sep).join('');
    return s.replace(sep, '.');
  }

  /**
   * Ubah teks angka jadi Number.
   * locale 'id'  : titik = ribuan, koma = desimal  (10.000.000,50)   <- default
   * locale 'en'  : koma = ribuan, titik = desimal  (10,000,000.50)
   * locale 'auto': tebak otomatis (kurang aman untuk angka ambigu)
   * Mendukung awalan "Rp"/"IDR", tanda minus, dan negatif dalam kurung (1.000).
   */
  function parseAmount(value, locale = 'id') {
    if (value === null || value === undefined) return 0;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw new Error(`Angka tidak valid: "${value}"`);
      return round2(value);
    }
    let s = String(value).replace(/[\s\u00A0]/g, '').replace(/^(rp\.?|idr)/i, '');
    if (s === '' || s === '-') return 0;
    let neg = false;
    if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
    if (s.startsWith('-')) { neg = true; s = s.slice(1); }
    if (!/^[0-9.,]+$/.test(s)) throw new Error(`Angka tidak valid: "${value}"`);

    let normalized;
    if (locale === 'en') normalized = s.replace(/,/g, '');
    else if (locale === 'auto') normalized = autoNormalize(s);
    else normalized = s.replace(/\./g, '').replace(',', '.');

    const n = Number(normalized);
    if (!Number.isFinite(n)) throw new Error(`Angka tidak valid: "${value}"`);
    return round2(neg ? -n : n);
  }

  /** Terima yyyy-mm-dd, dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy -> 'yyyy-mm-dd' atau null. */
  function parseDate(value) {
    if (!value) return null;
    const s = String(value).trim();
    let y, m, d, mt;
    if ((mt = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/))) { y = +mt[1]; m = +mt[2]; d = +mt[3]; }
    else if ((mt = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})/))) { d = +mt[1]; m = +mt[2]; y = +mt[3]; }
    else return null;
    const dt = new Date(Date.UTC(y, m - 1, d));
    if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
    return `${y}-${pad2(m)}-${pad2(d)}`;
  }

  /**
   * NPWP -> hanya digit. NPWP lama 15 digit diberi awalan "0" agar setara
   * format 16 digit (ASUMSI: verifikasi dengan ketentuan DJP terbaru).
   */
  function normalizeNpwp(value) {
    const digits = String(value || '').replace(/\D/g, '');
    if (digits.length === 15) return '0' + digits;
    return digits;
  }

  /** Nomor faktur/invoice -> huruf besar, buang semua tanda baca & spasi. */
  function normalizeInvoiceNo(value) {
    return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  // ------------------------------------------------------------ Mapping
  function mapRecords(rows, spec, opts, label, warnings) {
    if (!rows.length) throw new Error(`${label}: file kosong atau tidak ada baris data.`);
    const available = Object.keys(rows[0]).filter((k) => k !== '__row');
    const lookup = {};
    available.forEach((h) => { lookup[h.toLowerCase()] = h; });

    const col = (std, required) => {
      const wanted = spec.columns[std];
      if (!wanted) {
        if (required) throw new Error(`${label}: mapping kolom "${std}" belum diisi di config/mapping.json`);
        return null;
      }
      const actual = lookup[String(wanted).trim().toLowerCase()];
      if (!actual && required) {
        throw new Error(`${label}: kolom "${wanted}" tidak ditemukan. Kolom tersedia: ${available.join(', ')}`);
      }
      return actual || null;
    };
    const cInv = col('invoice_no', true);
    const cDpp = col('dpp', true);
    const cPpn = col('ppn', true);
    const cNpwp = col('npwp', false);
    const cDate = col('date', false);

    const records = [];
    for (const r of rows) {
      try {
        const invoice = r[cInv];
        if (!invoice) throw new Error('nomor dokumen kosong');
        const date = cDate ? parseDate(r[cDate]) : null;
        if (cDate && r[cDate] && !date) warnings.push({ source: label, row: r.__row, message: `Format tanggal tidak dikenali: "${r[cDate]}"` });
        records.push({
          row: r.__row,
          invoice_no: invoice,
          npwp: cNpwp ? normalizeNpwp(r[cNpwp]) : '',
          date,
          dpp: parseAmount(r[cDpp], opts.locale),
          ppn: parseAmount(r[cPpn], opts.locale),
          norm: {
            invoice_no: normalizeInvoiceNo(invoice),
            npwp: cNpwp ? normalizeNpwp(r[cNpwp]) : '',
          },
        });
      } catch (e) {
        warnings.push({ source: label, row: r.__row, message: `Baris dilewati: ${e.message}` });
      }
    }
    return records;
  }

  // -------------------------------------------------------- Rekonsiliasi
  /**
   * Cocokkan dua daftar record berdasarkan kunci (default: nomor dokumen + NPWP).
   * diff = A - B. Selisih <= tolerance dianggap pembulatan.
   */
  function reconcile(recA, recB, opts = {}) {
    const tol = opts.tolerance !== undefined && opts.tolerance !== null ? Number(opts.tolerance) : 10;
    const ppnRate = opts.ppnRate !== undefined && opts.ppnRate !== null ? Number(opts.ppnRate) : null;
    const keyFields = opts.keyFields || ['invoice_no', 'npwp'];
    const keyOf = (r) => keyFields.map((f) => r.norm[f] || '').join('|');

    const group = (recs) => {
      const m = new Map();
      for (const r of recs) {
        const k = keyOf(r);
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(r);
      }
      return m;
    };
    const side = (g) => (g ? {
      first: g[0],
      count: g.length,
      date: g[0].date,
      dpp: round2(g.reduce((s, r) => s + r.dpp, 0)),
      ppn: round2(g.reduce((s, r) => s + r.ppn, 0)),
    } : null);

    const gA = group(recA);
    const gB = group(recB);
    const keys = [...gA.keys(), ...[...gB.keys()].filter((k) => !gA.has(k))];

    const results = keys.map((key) => {
      const a = side(gA.get(key));
      const b = side(gB.get(key));
      const notes = [];
      const dDpp = round2((a ? a.dpp : 0) - (b ? b.dpp : 0));
      const dPpn = round2((a ? a.ppn : 0) - (b ? b.ppn : 0));
      let status;

      if (a && !b) { status = 'ONLY_IN_A'; notes.push('Tidak ditemukan di sumber B'); }
      else if (!a && b) { status = 'ONLY_IN_B'; notes.push('Tidak ditemukan di sumber A'); }
      else {
        const within = Math.abs(dDpp) <= tol && Math.abs(dPpn) <= tol;
        const exact = dDpp === 0 && dPpn === 0;
        const periodDiff = !!(a.date && b.date && a.date.slice(0, 7) !== b.date.slice(0, 7));

        if (a.count > 1 || b.count > 1) {
          status = 'DUPLICATE_KEY';
          notes.push(`Kunci muncul ${a.count}x di A dan ${b.count}x di B (nilai dijumlahkan)`);
          if (!within) notes.push('Total berbeda melebihi toleransi');
        } else if (!within) {
          status = 'AMOUNT_MISMATCH';
          if (Math.abs(dDpp) > tol) notes.push(`DPP berbeda ${dDpp}`);
          if (Math.abs(dPpn) > tol) notes.push(`PPN berbeda ${dPpn}`);
        } else if (periodDiff) {
          status = 'PERIOD_MISMATCH';
        } else {
          status = exact ? 'MATCH' : 'MATCH_ROUNDING';
          if (!exact) notes.push(`Selisih pembulatan (DPP ${dDpp}, PPN ${dPpn})`);
        }
        if (periodDiff) notes.push(`Masa berbeda: A ${a.date.slice(0, 7)} vs B ${b.date.slice(0, 7)}`);
      }

      if (ppnRate !== null) {
        [['A', a], ['B', b]].forEach(([lbl, s]) => {
          if (!s) return;
          const expected = round2(s.dpp * ppnRate);
          if (Math.abs(s.ppn - expected) > tol) notes.push(`PPN di ${lbl} tidak sesuai tarif ${ppnRate} (diharapkan ${expected}, tercatat ${s.ppn})`);
        });
      }

      const any = (a || b).first;
      return {
        status,
        invoice_no: (a ? a.first : b.first).invoice_no,
        npwp: any.norm.npwp || any.npwp || '',
        date_a: a ? a.date : null,
        date_b: b ? b.date : null,
        dpp_a: a ? a.dpp : null,
        dpp_b: b ? b.dpp : null,
        diff_dpp: dDpp,
        ppn_a: a ? a.ppn : null,
        ppn_b: b ? b.ppn : null,
        diff_ppn: dPpn,
        notes: notes.join('; '),
        row_a: a ? a.first.row : null,
        row_b: b ? b.first.row : null,
      };
    });

    return results;
  }

  function summarize(results, recA, recB) {
    const counts = {};
    STATUSES.forEach((s) => { counts[s] = 0; });
    results.forEach((r) => { counts[r.status]++; });
    const sum = (recs, f) => round2(recs.reduce((s, r) => s + r[f], 0));
    const ok = counts.MATCH + counts.MATCH_ROUNDING;
    return {
      counts,
      total_keys: results.length,
      matched_pct: results.length ? round2((ok / results.length) * 100) : 0,
      sum_dpp_a: sum(recA, 'dpp'),
      sum_dpp_b: sum(recB, 'dpp'),
      sum_ppn_a: sum(recA, 'ppn'),
      sum_ppn_b: sum(recB, 'ppn'),
      net_diff_dpp: round2(sum(recA, 'dpp') - sum(recB, 'dpp')),
      net_diff_ppn: round2(sum(recA, 'ppn') - sum(recB, 'ppn')),
    };
  }

  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  /**
   * Pipeline lengkap: teks CSV A + teks CSV B + config -> hasil.
   * `results` sudah berbentuk baris tabel recon_results (siap insert ke Postgres).
   */
  function run(textA, textB, config) {
    const warnings = [];
    const opts = { locale: 'id', tolerance: 10, ppnRate: null, ...config };
    const recA = mapRecords(parseCsv(textA), config.sourceA, opts, config.sourceA.label || 'Sumber A', warnings);
    const recB = mapRecords(parseCsv(textB), config.sourceB, opts, config.sourceB.label || 'Sumber B', warnings);
    const results = reconcile(recA, recB, opts);
    const summary = summarize(results, recA, recB);
    const runId = uuid();
    const discrepancy = results.filter((r) => r.status !== 'MATCH' && r.status !== 'MATCH_ROUNDING');
    return {
      run_id: runId,
      tolerance: opts.tolerance,
      total_a: recA.length,
      total_b: recB.length,
      summary,
      warnings,
      discrepancy_count: discrepancy.length,
      results: results.map((r) => ({ run_id: runId, ...r })),
    };
  }

  return { STATUSES, parseCsv, toCsv, parseAmount, parseDate, normalizeNpwp, normalizeInvoiceNo, mapRecords, reconcile, summarize, run };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = TaxRecon;
