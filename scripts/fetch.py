#!/usr/bin/env python3
"""Refresh the cached BGG collection + per-game detail XML.

    python3 scripts/fetch.py [--force]

Two-stage, because that is how the BGG XML API works:

1. /xmlapi2/collection returns HTTP 202 the first time ("queued"); we poll
   until it returns 200 with the real payload.
2. /xmlapi2/thing accepts at most 20 ids per request (50 returns HTTP 400),
   so the owned-game ids are fetched in batches of 20, spaced 6s apart to
   stay well inside BGG's rate limits.

curl is used rather than urllib because urllib hits IncompleteRead on these
responses under the Claude Code sandbox.
"""
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from common import RAW, load_creds

BATCH = 20          # BGG hard limit for /thing?id=
SPACING = 6         # seconds between requests
FORCE = "--force" in sys.argv


def curl(url, out, token):
    r = subprocess.run(
        ["curl", "-sS", "--http1.1", "--retry", "2",
         "-H", f"Authorization: Bearer {token}", "-o", str(out),
         "-w", "%{http_code}", url],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def fetch_collection(user, token, name="collection.xml", extra=""):
    """`extra` selects the subtype: base games by default, or expansions."""
    out = RAW / name
    if out.exists() and out.stat().st_size > 5000 and not FORCE:
        print(f"skip {out.name} (use --force to refetch)")
        return out
    url = (f"https://boardgamegeek.com/xmlapi2/collection?username={user}"
           "&own=1&stats=1" + extra)
    for attempt in range(12):
        code = curl(url, out, token)
        if code == "200" and out.stat().st_size > 5000:
            print(f"{name} {out.stat().st_size} bytes")
            return out
        # 202 = BGG queued the export; wait and ask again.
        print(f"  http={code}, waiting… ({attempt + 1})")
        time.sleep(10)
    raise SystemExit("collection never became ready")


def fetch_things(colls, token, prefix="thing"):
    ids = []
    for coll in colls:
        for i in ET.parse(coll).getroot().findall("item"):
            if i.get("objectid") not in ids:
                ids.append(i.get("objectid"))
    print(f"{len(ids)} owned items -> {prefix}_*.xml")
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        out = RAW / f"{prefix}_{i:04d}.xml"
        if out.exists() and out.stat().st_size > 5000 and not FORCE:
            print(f"skip {out.name}")
            continue
        url = ("https://boardgamegeek.com/xmlapi2/thing?id="
               + ",".join(chunk) + "&stats=1")
        for attempt in range(4):
            code = curl(url, out, token)
            if code == "200" and out.stat().st_size > 5000:
                try:
                    ET.parse(out)
                    break
                except ET.ParseError as e:
                    print(f"  bad xml: {e}")
            print(f"  retry {attempt} http={code}")
            time.sleep(8)
        print(f"{out.name} {out.stat().st_size}")
        if i + BATCH < len(ids):
            time.sleep(SPACING)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    c = load_creds()
    base = fetch_collection(c["BGG_USERNAME"], c["BGG_TOKEN"],
                            "collection.xml",
                            "&excludesubtype=boardgameexpansion")
    fetch_things([base], c["BGG_TOKEN"], "thing")
    # Expansions are a separate subtype query. They matter because an expansion
    # can change which player counts a base game plays well at.
    exp = fetch_collection(c["BGG_USERNAME"], c["BGG_TOKEN"],
                           "expansions.xml", "&subtype=boardgameexpansion")
    fetch_things([exp], c["BGG_TOKEN"], "exp")
    print("done — now run: python3 scripts/build.py")


if __name__ == "__main__":
    main()
