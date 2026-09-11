#!/usr/bin/env python3
"""Render the built report to a PNG for the README.

    python3 scripts/screenshot.py [--html reports/collection.html]
                                  [-o docs/screenshot.png]

Uses Playwright's Chromium when it is installed (that is what CI does), and
otherwise falls back to whatever Chrome is on the machine — so it works
locally without a 150 MB browser download.

The shot is deliberately clipped to the top of the page — the header, the
filter bar and the first handful of rows — because the point is to show what
the thing looks like, not to dump 85 rows into the README.
"""
import argparse
import sys
from pathlib import Path

from common import ROOT

WIDTH, HEIGHT = 1400, 980


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
        # apply the opening filters and lazy images time to decode.
        page.wait_for_timeout(1500)
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
             "--virtual-time-budget=4000",
             f"--screenshot={out}", src.as_uri()],
            capture_output=True, text=True)
    if not out.exists():
        print(r.stderr[-500:], file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="reports/collection.html")
    ap.add_argument("-o", "--out", default="docs/screenshot.png")
    a = ap.parse_args()

    src = ROOT / a.html
    if not src.exists():
        raise SystemExit(f"{src} not found — run scripts/report.py first")

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)

    if not (shoot_playwright(src, out) or shoot_chrome(src, out)):
        raise SystemExit(
            "No browser available. Either install Playwright\n"
            "  pip install playwright && playwright install chromium\n"
            "or install Google Chrome / Chromium.")

    kb = out.stat().st_size // 1024
    print(f"{out} ({WIDTH}x{HEIGHT}, {kb} KB)")


if __name__ == "__main__":
    main()
