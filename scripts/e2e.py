"""End-to-end check in headless Chrome: two students annotating live, a visitor, and the
admin adding footnotes; structural links within and across chapters.

Starts its own server on a throwaway database. Needs Playwright (not in requirements-dev,
since it's optional) and an installed Google Chrome:

    uv pip install playwright
    .venv/bin/python scripts/e2e.py [screenshot-dir]
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 8799
BASE = f"http://localhost:{PORT}"
REPO = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="e2e-shots-"))


def start_server(db_dir):
    env = {**os.environ, "DB_PATH": str(Path(db_dir) / "e2e.db"), "ADMIN_PASSWORD": "pw", "ADMIN_NAME": "Prof. A"}
    venv_python = REPO / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{BASE}/api/texts")
            return proc
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("server didn't start")


def admin_setup():
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(f"{BASE}/api/admin/login", data=json.dumps({"password": "pw"}).encode(),
                                 headers={"content-type": "application/json"})
    opener.open(req)
    boundary = "xyzzy"
    body = (REPO / "fixtures/sample.md").read_bytes()
    parts = []
    for name, value in [("title", "Sample Voyage"), ("slug", "sample"), ("passcode", "fish")]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="s.md"\r\n\r\n'.encode() + body + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"{BASE}/api/admin/texts", data=b"".join(parts),
                                 headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    try:
        opener.open(req)
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise


SELECT_JS = """([phrase, occurrence]) => {
  const root = document.getElementById('chapter');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const text = nodes.map((n) => n.data).join('');
  let i = -1;
  for (let k = 0; k <= occurrence; k++) { i = text.indexOf(phrase, i + 1); if (i < 0) return false; }
  const at = (off, end) => {
    let t = 0;
    for (const n of nodes) {
      if (off < t + n.length || (end && off === t + n.length)) return [n, off - t];
      t += n.length;
    }
  };
  const r = document.createRange();
  r.setStart(...at(i, false)); r.setEnd(...at(i + phrase.length, true));
  getSelection().removeAllRanges(); getSelection().addRange(r);
  root.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
  return true;
}"""


def select(page, phrase, occurrence=0):
    assert page.evaluate(SELECT_JS, [phrase, occurrence]), f"phrase not found: {phrase}"
    page.wait_for_selector("#toolbar:not([hidden])")


def join(page, name):
    page.click("#who button")
    page.fill("#join-form input[name=name]", name)
    page.fill("#join-form input[name=passcode]", "FISH")
    page.click("#join-form button.primary")
    page.wait_for_selector(f"#who strong:text('{name}')")


def annotate(page, phrase, button, comment):
    select(page, phrase)
    page.click(f"#toolbar button:text('{button}')")
    page.fill("#panel textarea[data-key=compose]", comment)
    page.click("#panel .compose button.primary")
    page.wait_for_selector("#panel .thread:not(.compose)")


def main():
    with tempfile.TemporaryDirectory() as db_dir:
        server = start_server(db_dir)
        try:
            run()
        finally:
            server.terminate()
    print(f"screenshots in {OUT}")


def run():
    admin_setup()
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        alice_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        bob_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        visitor_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        alice, bob, visitor = alice_ctx.new_page(), bob_ctx.new_page(), visitor_ctx.new_page()
        for pg in (alice, bob, visitor):
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
            pg.goto(f"{BASE}/t/sample#2")
            pg.wait_for_selector("#chapter p")

        join(alice, "Alice")
        join(bob, "Bob")

        annotate(alice, "industrious", "Vocab", "What does this mean here?")
        annotate(alice, "industrious beyond any I have since encountered", "Comment",
                 "Strong claim. See https://example.com/notes.")

        # Bob sees both highlights live, without reloading.
        bob.wait_for_selector(".ann.hl-vocab.hl-comm", timeout=5000)
        bob.click(".ann.hl-vocab.hl-comm")
        assert bob.locator("#panel .thread").count() == 2, "overlap should open both threads"
        bob.fill("#panel .layer-vocab textarea[data-key^=reply]", "Hard-working, diligent.")
        bob.click("#panel .layer-vocab .reply button")
        bob.wait_for_selector("#panel .layer-vocab .message .body:text('Hard-working, diligent.')")
        assert bob.locator("#panel .layer-vocab .message .link-button:text('edit')").count() == 1, \
            "Bob should only be able to edit his own reply"

        # Alice, panel open, gets Bob's reply live; her half-typed reply survives the refresh.
        alice.click("#panel .panel-close")
        alice.click(".ann.hl-vocab >> nth=0")
        alice.fill("#panel .layer-vocab textarea[data-key^=reply]", "half-typed draft")
        alice.wait_for_selector("#panel .message .body:text('Hard-working, diligent.')", timeout=5000)
        draft = alice.input_value("#panel .layer-vocab textarea[data-key^=reply]")
        assert draft == "half-typed draft", f"draft lost: {draft!r}"

        # Visitor: sees highlights, no edit controls, selection offers only "Join".
        visitor.wait_for_selector(".ann.hl-vocab", timeout=5000)
        visitor.click(".ann.hl-vocab >> nth=0")
        assert visitor.locator("#panel .link-button:text('edit')").count() == 0
        assert visitor.locator("#panel textarea").count() == 0
        select(visitor, "strand")
        assert visitor.inner_text("#toolbar").strip() == "Join to annotate"

        bob.screenshot(path=str(OUT / "threads.png"))
        margins_and_links(browser, alice, bob, errors)

        browser.close()
    if errors:
        print("JS errors:", *errors, sep="\n  ")
        raise SystemExit(1)
    print("e2e ok")


def margins_and_links(browser, alice, bob, errors):
    admin_ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    admin = admin_ctx.new_page()
    admin.on("pageerror", lambda e: errors.append(str(e)))
    admin.goto(f"{BASE}/admin")
    admin.fill("input[name=password]", "pw")
    admin.click("#login-form button")
    admin.wait_for_selector("#admin-section:not([hidden])")
    admin.goto(f"{BASE}/t/sample#2")
    admin.wait_for_selector("#chapter p")
    assert "Prof. A" in admin.inner_text("#who")

    # Footnote: admin-only toolbar button; appears live for Alice as a quiet marker.
    select(admin, "awning of sailcloth")
    admin.click("#toolbar button:text('Footnote')")
    admin.fill("#panel textarea[data-key=compose]", "A canvas shelter, as on a ship's deck.")
    admin.click("#panel .compose button.primary")
    alice.wait_for_selector(".fn-mark", timeout=5000)
    assert alice.locator("#toolbar button:text('Footnote')").count() == 0
    alice.hover(".fn-mark")
    alice.wait_for_selector("#margin-left .fn-note.show")
    note_top = alice.evaluate("document.querySelector('#margin-left .fn-note.show').getBoundingClientRect().top")
    mark_top = alice.evaluate("document.querySelector('.fn-mark').getBoundingClientRect().top")
    assert abs(note_top - mark_top) < 20, (note_top, mark_top)

    # Offsets still line up with a .ui marker in the text: the server re-checks the quote.
    alice.mouse.move(0, 0)
    annotate(alice, "adjudicate", "Vocab", "")

    # Structural links: outline items -> passages. Banner guides the second selection.
    def link(page, anchor, dest, dest_chapter=None):
        select(page, anchor)
        page.click("#toolbar button:text('Link…')")
        page.wait_for_selector("#banner:not([hidden])")
        if dest_chapter:
            page.select_option("#chapter-select", dest_chapter)
            page.wait_for_function(f"location.hash === '#{dest_chapter}'")
            page.wait_for_selector("#chapter p")
        select(page, dest)
        page.click("#toolbar button:text('Link here')")
        page.wait_for_selector("#banner", state="hidden")

    link(alice, "The market and its customs", "The market was held each seventh day upon the strand.")
    link(alice, "A storm at sea", "We had not been three days from port when the sky grew livid")
    alice.wait_for_selector("#margin-right .struct-num .struct-go:text-is('II')")
    assert alice.locator("#margin-right .struct-anchor-num").count() == 2
    bob.wait_for_selector("#margin-right .struct-num .struct-go:text-is('II')", timeout=5000)
    assert bob.locator("#margin-right .struct-del").count() == 0, "Bob can't delete Alice's links"

    # Bar spans the destination passage's height.
    bar_h = alice.evaluate("""[...document.querySelectorAll('#margin-right .struct-bar')]
        .map(b => b.getBoundingClientRect().height)""")
    assert all(h > 20 for h in bar_h), bar_h  # one-line destinations: ~1 line tall

    alice.hover(".fn-mark")
    alice.screenshot(path=str(OUT / "margins.png"))

    # Cross-chapter link (anchor in chapter I's outline, destination in chapter II).
    alice.goto(f"{BASE}/t/sample#2")
    alice.wait_for_selector("#chapter p")
    link(alice, "Arrival at the island", "The island was smaller than I had supposed", dest_chapter="3")
    alice.wait_for_selector("#margin-right .struct-num .struct-go:text-is('III')")
    alice.click("#margin-right .struct-num .struct-go")
    alice.wait_for_function("location.hash === '#2'")
    alice.wait_for_selector(".ann.link-anchor")
    alice.go_back()
    alice.wait_for_function("location.hash === '#3'")
    alice.wait_for_selector("#margin-right .struct-num")

    # Clicking anchor text follows the link.
    alice.goto(f"{BASE}/t/sample#2")
    alice.wait_for_selector(".ann.link-anchor")
    alice.set_viewport_size({"width": 1400, "height": 400})
    alice.click(".ann.link-anchor >> text=A storm at sea")
    alice.wait_for_function("scrollY > 100")

    # Admin can delete Alice's link from the margin.
    admin.reload()
    admin.wait_for_selector("#margin-right .struct-label")
    admin.on("dialog", lambda d: d.accept())
    before = admin.locator("#margin-right .struct-num").count()
    admin.hover("#margin-right .struct-num >> nth=0")
    admin.click("#margin-right .struct-num .struct-del >> nth=0")
    admin.wait_for_function(f"document.querySelectorAll('#margin-right .struct-num').length === {before - 1}")

    narrow = browser.new_context(viewport={"width": 420, "height": 800}).new_page()
    narrow.goto(f"{BASE}/t/sample#2")
    narrow.wait_for_selector(".fn-mark")
    narrow.click(".fn-mark")
    narrow.screenshot(path=str(OUT / "narrow.png"))


if __name__ == "__main__":
    main()
