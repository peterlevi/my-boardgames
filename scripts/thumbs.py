#!/usr/bin/env python3
"""Cache and downscale every game thumbnail so reports can inline them.

    python3 scripts/thumbs.py [--force]

Slack (and anything else with a strict image policy) renders the HTML report
but blocks its hotlinked BGG images, so a report meant to travel has to carry
its pictures as data URIs. Downloading them once into data/thumbs/ keeps that
free afterwards.

Images come from BGG's image CDN rather than the XML API. They are fetched in
one curl run over a reused connection instead of 265 separate processes, and
already-cached files are skipped, so a re-run costs nothing.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

from common import ROOT, load_games

THUMBS = ROOT / "data" / "thumbs"
ORIG = THUMBS / "orig"
WIDTH = 96      # 2x the 48px the report renders, for retina
QUALITY = 72
FORCE = "--force" in sys.argv


def download(games):
    """One curl invocation for everything missing, so the connection is reused."""
    jobs = []
    for g in games:
        if not g["thumbnail"]:
            continue
        ext = Path(g["thumbnail"].split("?")[0]).suffix.lower() or ".jpg"
        dest = ORIG / f'{g["id"]}{ext}'
        if dest.exists() and dest.stat().st_size > 500 and not FORCE:
            continue
        jobs.append((g["thumbnail"], dest))
    if not jobs:
        print("all originals cached")
        return
    cfg = "\n".join(f'url = "{u}"\noutput = "{d}"' for u, d in jobs)
    conf = THUMBS / "_fetch.conf"
    conf.write_text(cfg)
    print(f"downloading {len(jobs)} thumbnails…")
    subprocess.run(["curl", "-sS", "--compressed", "--retry", "2",
                    "--parallel", "--parallel-max", "4", "-K", str(conf)],
                   check=True)
    conf.unlink()


def downscale(games):
    made = 0
    for g in games:
        if not g["thumbnail"]:
            continue
        ext = Path(g["thumbnail"].split("?")[0]).suffix.lower() or ".jpg"
        src, dest = ORIG / f'{g["id"]}{ext}', THUMBS / f'{g["id"]}.jpg'
        if not src.exists():
            continue
        if dest.exists() and not FORCE:
            continue
        try:
            im = Image.open(src)
            # Flatten transparency onto white; the report shows them on a light
            # card and JPEG has no alpha channel anyway.
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            h = max(1, round(im.height * WIDTH / im.width))
            im.resize((WIDTH, h), Image.LANCZOS).save(
                dest, "JPEG", quality=QUALITY, optimize=True)
            made += 1
        except Exception as e:  # noqa: BLE001
            print(f"  skip {g['name']}: {e}")
    print(f"{made} thumbnails downscaled")


def main():
    ORIG.mkdir(parents=True, exist_ok=True)
    games = load_games()
    download(games)
    downscale(games)
    total = sum(f.stat().st_size for f in THUMBS.glob("*.jpg"))
    print(f"{len(list(THUMBS.glob('*.jpg')))} cached, {total // 1024} KB total")


if __name__ == "__main__":
    main()
