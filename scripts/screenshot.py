#!/usr/bin/env python3
"""Render the built report to a PNG for the README.

    python3 scripts/screenshot.py [--html reports/collection.html]
                                  [-o site/screenshot.png]
                                  [--expand "Yellow & Yangtze"]

Uses Playwright's Chromium when it is installed (that is what CI does), and
otherwise falls back to whatever Chrome is on the machine — so it works
locally without a 150 MB browser download.

The shot is deliberately clipped to the top of the page — the header, the
filter bar and the first handful of rows — because the point is to show what
the thing looks like, not to dump 85 rows into the README.

`--expand NAME` clicks that game's row first, so the shot shows the detail
panel as you actually meet it: scrolled up under the header by the row-expand
tween. The click is injected into a throwaway copy of the HTML rather than
driven through the browser, so it works the same under Playwright and under
the plain-Chrome fallback, which cannot script the page.
"""
import argparse
import sys
from pathlib import Path

from common import ROOT

WIDTH, HEIGHT = 1400, 980

EXPAND_JS = """
<script>
window.addEventListener('load', function () {
  var want = %s;
  setTimeout(function () {
    var rows = document.querySelectorAll('tbody tr.game-row');
    for (var i = 0; i < rows.length; i++) {
      var cell = rows[i].querySelector('.game');
      if (cell && cell.textContent.trim() === want) {
        var row = rows[i];
        row.click();
        // Jump to the tween's destination instead of trusting the animation:
        // headless Chrome runs on virtual time and may shoot mid-scroll.
        setTimeout(function () {
          window.scrollTo(0, Math.max(0, window.pageYOffset +
            row.getBoundingClientRect().top - headerPad()));
        }, 400);
        break;
      }
    }
  }, 400);
});
</script>
"""


def check_not_blank(out, width, height):
    """Refuse to hand back an image that is obviously empty.

    The page starts at `opacity: 0` and its own script fades it in, so a
    capture taken before that script finishes is a single flat colour — and a
    flat PNG compresses to a few kilobytes where a real one is hundreds. That
    is exactly what the plain-Chrome fallback produces for `--expand`: it
    cannot drive the page, and it exits 0 with a blank file.

    Silent success is the dangerous part. The README's screenshots are
    published rather than committed, so nothing downstream would notice a
    blank one; a build that fails is much better than a site that quietly
    shows nothing. This is a smoke test, not a validator — it catches "the
    renderer produced nothing", not "the layout is subtly wrong".
    """
    size = out.stat().st_size if out.exists() else 0
    floor = max(20_000, width * height // 100)
    if size < floor:
        raise SystemExit(
            f"{out} is {size} bytes for {width}x{height} — under the {floor} "
            f"byte floor, so it is almost certainly a blank capture. The page "
            f"fades itself in, so this usually means the shot was taken "
            f"before its script ran. --expand needs Playwright; the plain "
            f"Chrome fallback cannot drive the page."
        )


def with_expand(src, name):
    """A throwaway copy of the page that opens one game on load."""
    import json
    html = src.read_text(encoding="utf-8")
    tmp = src.with_name(src.stem + ".expanded.html")
    tmp.write_text(html.replace("</body>", EXPAND_JS % json.dumps(name) + "</body>"),
                   encoding="utf-8")
    return tmp


def shoot_playwright(src, out):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                                device_scale_factor=2)
        page.goto(src.as_uri())
        # The table is rendered server-side, but give the script its moment to
        # apply the opening filters, run any injected click, and let the lazy
        # images decode.
        page.wait_for_timeout(2200)
        page.screenshot(path=str(out))
        browser.close()
    return True


CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
]


def shoot_chrome(src, out):
    """Fallback for a machine with Chrome but no Playwright."""
    import shutil
    import subprocess
    import tempfile

    exe = next((c for c in CHROMES
                if Path(c).exists() or shutil.which(c)), None)
    if not exe:
        return False
    with tempfile.TemporaryDirectory() as profile:
        r = subprocess.run(
            [exe, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={profile}",
             f"--window-size={WIDTH},{HEIGHT}",
             "--virtual-time-budget=6000",
             f"--screenshot={out}", src.as_uri()],
            capture_output=True, text=True)
    if not out.exists():
        print(r.stderr[-500:], file=sys.stderr)
        return False
    return True


def clear(out):
    """A stale file from a previous run would otherwise read as success —
    shoot_chrome only checks that the path exists afterwards."""
    if out.exists():
        out.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="reports/collection.html")
    ap.add_argument("-o", "--out", default="site/screenshot.png")
    ap.add_argument("--expand", metavar="NAME",
                    help="click this game's row before shooting")
    a = ap.parse_args()

    src = ROOT / a.html
    if not src.exists():
        raise SystemExit(f"{src} not found — run scripts/report.py first")

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)

    clear(out)
    tmp = with_expand(src, a.expand) if a.expand else None
    shot_src = tmp or src
    try:
        ok = shoot_playwright(shot_src, out) or shoot_chrome(shot_src, out)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    if not ok:
        raise SystemExit(
            "No browser available. Either install Playwright\n"
            "  pip install playwright && playwright install chromium\n"
            "or install Google Chrome / Chromium.")

    check_not_blank(out, WIDTH, HEIGHT)
    kb = out.stat().st_size // 1024
    print(f"{out} ({WIDTH}x{HEIGHT}, {kb} KB)")


if __name__ == "__main__":
    main()
