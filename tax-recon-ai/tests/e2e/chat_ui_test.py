"""
Uji end-to-end web/chat.html di Chromium (Playwright) terhadap mock-n8n.js.

  node tests/e2e/mock-n8n.js &
  python3 tests/e2e/chat_ui_test.py

Butuh: pip install playwright && playwright install chromium
"""
import base64, json, pathlib, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
HTML = (ROOT / "web" / "chat.html").as_uri()
URL = "http://127.0.0.1:5679/webhook/test/chat"
SHOTS = ROOT / "docs" / "evidence"
SHOTS.mkdir(parents=True, exist_ok=True)
results = []

def check(name, cond, detail=""):
    results.append({"test": name, "pass": bool(cond), "detail": detail})
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def open_chat(browser, user, pwd, url=URL, scheme="light"):
    ctx = browser.new_context(viewport={"width": 760, "height": 720}, color_scheme=scheme)
    page = ctx.new_page()
    page.goto(f"{HTML}?url={url}")
    page.fill("#user", user); page.fill("#pass", pwd); page.click("#connect")
    page.wait_for_selector("#chat", state="visible")
    return ctx, page

def wait_replies(page, n_total):
    page.wait_for_function(
        "n => document.querySelectorAll('#messages .msg:not(.user)').length >= n && !document.querySelector('.dots')", arg=n_total, timeout=8000)

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])

    # 1. Login benar + pertanyaan dari chip
    ctx, page = open_chat(browser, "red-pika", "test-pass")
    check("Halaman chat tampil setelah login", page.is_visible("#chat") and not page.is_visible("#setup"))
    check("Password dikosongkan dari form setelah login", page.input_value("#pass") == "")
    page.click("text=Ringkasan rekonsiliasi terakhir"); wait_replies(page, 2)
    page.click("text=Tampilkan 5 selisih terbesar"); wait_replies(page, 3)
    text = page.inner_text("#messages")
    check("Jawaban ringkasan muncul", "perlu ditindaklanjuti" in text)
    check("Jawaban 5 selisih terbesar memuat faktur ...99 (terbesar)", "010.000-26.09000099" in text)
    check("Format tebal/kode dirender (bukan tanda * atau `)", page.locator("#messages strong").count() >= 1 and page.locator("#messages code").count() >= 5)
    page.screenshot(path=str(SHOTS / "chat-sukses-light.png"))

    # 2. Kirim teks berbahaya, UI tidak boleh mengeksekusi
    page.fill("#input", '<img src=x onerror="window.__xss=1"> **uji**'); page.press("#input", "Enter"); wait_replies(page, 4)
    check("Tidak ada elemen <img> berbahaya di DOM", page.locator("#messages img").count() == 0)
    check("Skrip tidak tereksekusi (window.__xss kosong)", page.evaluate("window.__xss") is None)
    ctx.close()

    # 3. Login salah
    ctx, page = open_chat(browser, "red-pika", "salah", scheme="dark")
    page.click("text=Ringkasan rekonsiliasi terakhir")
    page.wait_for_selector(".msg.err", timeout=8000)
    check("Login salah menampilkan pesan 'Login ditolak'", "Login ditolak" in page.inner_text(".msg.err"))
    page.screenshot(path=str(SHOTS / "chat-login-salah-dark.png"))
    ctx.close()

    # 4. Server tidak terjangkau
    ctx, page = open_chat(browser, "red-pika", "test-pass", url="http://127.0.0.1:5999/x")
    page.click("text=Ringkasan rekonsiliasi terakhir")
    page.wait_for_selector(".msg.err", timeout=8000)
    check("Server mati menampilkan pesan koneksi", "Tidak bisa terhubung" in page.inner_text(".msg.err"))
    ctx.close()
    browser.close()

# 5. Periksa apa yang diterima server (kontrak Chat Trigger)
log = json.loads((pathlib.Path(__file__).parent / "mock-requests.json").read_text())
good = [e for e in log if e["authOk"]]
expect = "Basic " + base64.b64encode(b"red-pika:test-pass").decode()
check("Semua request sukses membawa header Basic Auth yang benar", len(good) >= 3 and all(e["authOk"] for e in good))
check("Body memakai kontrak n8n (action=sendMessage, sessionId, chatInput)",
      all(e["body"] and e["body"].get("action") == "sendMessage" and e["body"].get("sessionId") and e["body"].get("chatInput") for e in good))
check("Content-Type application/json", all("application/json" in (e["contentType"] or "") for e in good))
sess = {e["body"]["sessionId"] for e in good}
check("sessionId konsisten dalam satu percakapan (memori Postgres bergantung ini)", len(sess) == 1, f"{len(sess)} sessionId unik")
check("Request login salah ditolak server (authOk=false tercatat)", any(not e["authOk"] for e in log))

(pathlib.Path(__file__).parent / "ui-results.json").write_text(json.dumps(results, indent=2))
failed = [r for r in results if not r["pass"]]
print(f"\n{len(results) - len(failed)}/{len(results)} lolos")
sys.exit(1 if failed else 0)
