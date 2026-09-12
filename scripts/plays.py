#!/usr/bin/env python3
"""Cache the play log, for "last played" and a cross-check on play counts.

    python3 scripts/plays.py

The collection export carries how *many* times you have played a game but not
*when*, so the play log is a separate endpoint: `/xmlapi2/plays`, a hundred
plays per page, newest first. A few hundred plays is a handful of requests,
and they are spaced like every other call here.

Pages are re-fetched every run rather than cached, because a new play lands at
the top and shifts everything down — a cached page 2 would silently go stale.
The parsed result is written to `data/plays.json` as
`{game id: {"last": "YYYY-MM-DD", "n": plays}}`.
"""
import json
import subprocess
import xml.etree.ElementTree as ET
from time import sleep

from common import ROOT, load_creds

OUT = ROOT / "data" / "plays.json"
SPACING = 4          # seconds between pages
MAX_PAGES = 40       # 4000 plays; a guard against an endless loop


def fetch_page(user, token, page):
    url = (f"https://boardgamegeek.com/xmlapi2/plays?username={user}"
           f"&page={page}")
    r = subprocess.run(
        ["curl", "-sS", "--http1.1", "--retry", "2", "--max-time", "60",
         "-H", f"Authorization: Bearer {token}", url],
        capture_output=True, text=True)
    return r.stdout


def main():
    creds = load_creds()
    user, token = creds["BGG_USERNAME"], creds["BGG_TOKEN"]
    games, total, seen = {}, None, 0
    for page in range(1, MAX_PAGES + 1):
        xml = fetch_page(user, token, page)
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            print(f"  page {page}: unparseable, stopping")
            break
        if total is None:
            total = int(root.get("total") or 0)
            print(f"  {total} plays logged")
        plays = root.findall("play")
        if not plays:
            break
        for p in plays:
            date = p.get("date") or ""
            qty = int(p.get("quantity") or 1)
            for item in p.findall("item"):
                gid = item.get("objectid")
                if not gid:
                    continue
                rec = games.setdefault(gid, {"last": "", "n": 0})
                rec["n"] += qty
                # Pages arrive newest first, so the first date wins; compare
                # anyway rather than trusting the ordering.
                if date and date > rec["last"]:
                    rec["last"] = date
        seen += len(plays)
        print(f"  page {page}: {len(plays)} plays ({seen}/{total})")
        if seen >= (total or 0):
            break
        sleep(SPACING)
    OUT.write_text(json.dumps(games, indent=1, sort_keys=True))
    dated = sum(1 for v in games.values() if v["last"])
    print(f"{len(games)} games played, {dated} with a date -> {OUT}")


if __name__ == "__main__":
    main()
