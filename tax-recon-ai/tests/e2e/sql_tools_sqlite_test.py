"""
Uji LOGIKA 3 tool SQL chatbot memakai SQLite.

PENTING: ini bukan uji Postgres. Query diambil apa adanya dari n8n/workflow-2-chatbot.json,
lalu diterjemahkan secara mekanis ke SQLite ($1 -> :p1, ILIKE -> LIKE, buang ::text/::int).
Yang diuji: filter, urutan, pemilihan run terbaru, parameterisasi (anti SQL injection).
Yang TIDAK diuji: kompatibilitas sintaks/tipe Postgres. Itu harus dicek di Postgres sungguhan.
"""
import csv, json, pathlib, re, sqlite3, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
wf = json.loads((ROOT / "n8n" / "workflow-2-chatbot.json").read_text())
queries = {n["name"]: n["parameters"]["query"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.postgresTool"}

def to_sqlite(q):
    q = re.sub(r"\$(\d)(::\w+)?", r":p\1", q)
    return q.replace("ILIKE", "LIKE")

out = tempfile.mkdtemp()
subprocess.run(["node", str(ROOT / "scripts" / "run-local.js"), "--out", out], check=True, capture_output=True)
rows = list(csv.DictReader(open(pathlib.Path(out) / "hasil_rekonsiliasi.csv")))

db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE recon_runs (run_id TEXT PRIMARY KEY, created_at TEXT, tolerance REAL, total_a INT, total_b INT, summary TEXT, ai_explanation TEXT);
CREATE TABLE recon_results (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, status TEXT, invoice_no TEXT, npwp TEXT,
  date_a TEXT, date_b TEXT, dpp_a REAL, dpp_b REAL, diff_dpp REAL, ppn_a REAL, ppn_b REAL, diff_ppn REAL, notes TEXT, row_a INT, row_b INT);
""")
nz = lambda v: None if v == "" else v
# run LAMA (harus diabaikan semua tool)
db.execute("INSERT INTO recon_runs VALUES ('OLD','2026-01-01T00:00:00',10,1,1,'{}','lama')")
db.execute("INSERT INTO recon_results (run_id,status,invoice_no,diff_dpp,diff_ppn) VALUES ('OLD','AMOUNT_MISMATCH','INV-LAMA-9999',999999999,0)")
# run TERBARU = data contoh nyata
db.execute("INSERT INTO recon_runs VALUES ('NEW','2026-10-14T00:00:00',10,6,7,'{\"matched_pct\":28.57}','baru')")
for r in rows:
    db.execute("INSERT INTO recon_results (run_id,status,invoice_no,npwp,date_a,date_b,dpp_a,dpp_b,diff_dpp,ppn_a,ppn_b,diff_ppn,notes,row_a,row_b) VALUES ('NEW',?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               [nz(r[k]) for k in ["status","invoice_no","npwp","date_a","date_b","dpp_a","dpp_b","diff_dpp","ppn_a","ppn_b","diff_ppn","notes","row_a","row_b"]])

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

q = lambda name, params=(): db.execute(to_sqlite(queries[name]), {f'p{i + 1}': v for i, v in enumerate(params)}).fetchall()

# ringkasan_terakhir
r = q("ringkasan_terakhir")
check("ringkasan_terakhir mengembalikan 1 baris run TERBARU", len(r) == 1 and r[0][0] == "NEW", r[0][0])

# cari_selisih
r = q("cari_selisih", ("SEMUA", 50))
inv = [x[0] for x in r]
check("cari_selisih SEMUA: hanya run terbaru (INV-LAMA-9999 tidak muncul)", "INV-LAMA-9999" not in inv)
check("cari_selisih SEMUA: MATCH murni tidak ikut, jumlah = 6", len(r) == 6, f"{len(r)} baris")
mags = [abs(x[5] or 0) + abs(x[8] or 0) for x in r]
check("cari_selisih: urut selisih terbesar ke terkecil", mags == sorted(mags, reverse=True), str([int(m) for m in mags]))
check("cari_selisih: peringkat 1 = faktur ...99 (ONLY_IN_B)", r[0][0].endswith("99") and r[0][2] == "ONLY_IN_B")
check("cari_selisih filter ONLY_IN_A -> 1 baris", len(q("cari_selisih", ("ONLY_IN_A", 50))) == 1)
check("cari_selisih LIMIT 2 -> 2 baris", len(q("cari_selisih", ("SEMUA", 2))) == 2)
check("cari_selisih status tidak dikenal -> 0 baris (tidak error)", len(q("cari_selisih", ("BUKAN_STATUS", 10))) == 0)

# cari_dokumen
r = q("cari_dokumen", ("0002",))
check("cari_dokumen '0002' -> 1 dokumen AMOUNT_MISMATCH", len(r) == 1 and r[0][2] == "AMOUNT_MISMATCH" and r[0][10] == 55000.0)
check("cari_dokumen sebagian nomor '26.09000006' -> DUPLICATE_KEY", q("cari_dokumen", ("26.09000006",))[0][2] == "DUPLICATE_KEY")
check("cari_dokumen tidak menemukan data lama (INV-LAMA)", len(q("cari_dokumen", ("LAMA",))) == 0)
evil = "'; DROP TABLE recon_results; --"
check("cari_dokumen payload SQL injection -> 0 baris", len(q("cari_dokumen", (evil,))) == 0)
check("Tabel recon_results masih utuh setelah payload injection", db.execute("SELECT COUNT(*) FROM recon_results").fetchone()[0] == 8)

failed = [x for x in results if not x[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} lolos")
pathlib.Path(__file__).with_name("sql-results.json").write_text(json.dumps([{"test": a, "pass": b, "detail": c} for a, b, c in results], indent=2))
sys.exit(1 if failed else 0)
