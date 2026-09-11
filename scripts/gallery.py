#!/usr/bin/env python3
"""Cache a handful of gallery image URLs per game.

    python3 scripts/gallery.py [--force] [--limit N]

BGG's XML API gives exactly one image per game — the box art. The site's own
gallery endpoint (api.geekdo.com, no auth) gives the rest, which is where the
component and in-play shots live. Only the URLs are cached, not the bytes: the
report loads them when a row is expanded, so nothing is downloaded for the 241
games you did not open, and the file stays a sane size.

One consequence, stated plainly: the expanded panel's images are the only part
of the report that needs the network. They will not appear where external
images are blocked — Slack's preview, for one — which is also where the panel
cannot be opened at all, so nothing is lost there.
"""
import argparse
import json
import subprocess
import sys
import time

from common import ROOT, load_games

OUT = ROOT / "data" / "gallery"
API = ("https://api.geekdo.com/api/images?ajax=1&gallery=game&nosession=1"
       "&objectid={id}&objecttype=thing&pageid=1&showcount=8&size=large"
       "&sort=hot")


def fetch(gid):
    r = subprocess.run(
        ["curl", "-sS", "--compressed", "-A", "Mozilla/5.0", "--retry", "2",
         API.format(id=gid)], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-200:])
    data = json.loads(r.stdout)
    out = []
    for im in data.get("images", [])[:6]:
        url = im.get("imageurl_lg") or im.get("imageurl")
        if url:
            out.append({"u": url, "c": (im.get("caption") or "").strip()[:120]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sleep", type=float, default=0.4)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    todo = [g for g in load_games()
            if not g["is_expansion"]
            and (a.force or not (OUT / f'{g["id"]}.json').exists())]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        print("gallery cache is current")
        return

    print(f"fetching gallery URLs for {len(todo)} game(s)", flush=True)
    ok = bad = 0
    for i, g in enumerate(todo, 1):
        try:
            imgs = fetch(g["id"])
            (OUT / f'{g["id"]}.json').write_text(json.dumps(imgs))
            ok += 1
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"  {g['name']}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(a.sleep)
    print(f"done: {ok} cached, {bad} failed")


if __name__ == "__main__":
    main()
