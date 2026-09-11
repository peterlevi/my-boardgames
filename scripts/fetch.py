#!/usr/bin/env python3
"""Refresh the cached BGG collection and per-game detail XML.

    python3 scripts/fetch.py            # resync: collection always, new games only
    python3 scripts/fetch.py --full     # also refetch every game's details

Designed to be re-run regularly and cost almost nothing when little has
changed:

* The two collection exports are **always** refetched — they are the source of
  truth for what you own, and they carry your play counts and your own ratings,
  all of which change.
* Game details are cached one file per game in `data/raw/things/<id>.xml`, so a
  resync only fetches genuinely new games. (They used to be cached in batches
  of twenty keyed by position, which silently broke the moment the collection
  changed size: the batches shifted and new games were never fetched.)

Two BGG quirks shape this: `/xmlapi2/collection` answers `202` the first time
and queues the export, so it has to be polled; and `/xmlapi2/thing` accepts at
most 20 ids per request, so new games are fetched in batches of 20 and the
response is split into per-id files. Requests are spaced to stay well inside
BGG's rate limits — please leave that in.

curl is used rather than urllib because urllib hits IncompleteRead on these
responses under some sandboxes.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from time import sleep

from common import RAW, load_creds

THINGS = RAW / "things"
BATCH = 20          # BGG's hard limit for /thing?id=
SPACING = 6         # seconds between requests
FULL = "--full" in sys.argv


def curl(url, out, token):
    r = subprocess.run(
        ["curl", "-sS", "--http1.1", "--retry", "2",
         "-H", f"Authorization: Bearer {token}", "-o", str(out),
         "-w", "%{http_code}", url],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def fetch_collection(user, token, name, extra=""):
    """`extra` selects the subtype: base games by default, or expansions."""
    out = RAW / name
    url = (f"https://boardgamegeek.com/xmlapi2/collection?username={user}"
           "&own=1&stats=1" + extra)
    for attempt in range(12):
        code = curl(url, out, token)
        if code == "200" and out.stat().st_size > 5000:
            print(f"  {name}: {out.stat().st_size} bytes")
            return out
        # 202 = BGG queued the export; wait and ask again.
        print(f"  {name}: http {code}, waiting… ({attempt + 1}/12)")
        sleep(10)
    raise SystemExit(f"{name} never became ready")


def owned_ids(*collections):
    ids = []
    for coll in collections:
        for it in ET.parse(coll).getroot().findall("item"):
            if it.get("objectid") not in ids:
                ids.append(it.get("objectid"))
    return ids


def fetch_things(ids, token):
    """Fetch details for ids we do not already have, 20 per request."""
    THINGS.mkdir(parents=True, exist_ok=True)
    missing = [i for i in ids
               if FULL or not (THINGS / f"{i}.xml").exists()
               or (THINGS / f"{i}.xml").stat().st_size < 200]
    if not missing:
        print(f"  details: all {len(ids)} cached, nothing to fetch")
        return
    print(f"  details: {len(missing)} to fetch "
          f"({len(ids) - len(missing)} already cached)")

    tmp = RAW / "_batch.xml"
    for i in range(0, len(missing), BATCH):
        chunk = missing[i:i + BATCH]
        url = ("https://boardgamegeek.com/xmlapi2/thing?id="
               + ",".join(chunk) + "&stats=1")
        for attempt in range(4):
            code = curl(url, tmp, token)
            if code == "200" and tmp.exists() and tmp.stat().st_size > 500:
                try:
                    root = ET.parse(tmp).getroot()
                    break
                except ET.ParseError as e:
                    print(f"    bad xml: {e}")
            print(f"    retry {attempt + 1}/4 (http {code})")
            sleep(8)
        else:
            raise SystemExit(f"could not fetch ids {chunk}")

        # Split the batch into one stable file per game.
        for it in root.findall("item"):
            wrapper = ET.Element("items")
            wrapper.append(it)
            ET.ElementTree(wrapper).write(THINGS / f'{it.get("id")}.xml',
                                          encoding="utf-8", xml_declaration=True)
        print(f"    {min(i + BATCH, len(missing))}/{len(missing)}")
        if i + BATCH < len(missing):
            sleep(SPACING)
    tmp.unlink(missing_ok=True)


def prune(ids):
    """Drop details for games no longer in the collection."""
    keep = set(ids)
    gone = [f for f in THINGS.glob("*.xml") if f.stem not in keep]
    for f in gone:
        f.unlink()
    if gone:
        print(f"  pruned {len(gone)} game(s) no longer owned")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    c = load_creds()
    user, token = c["BGG_USERNAME"], c["BGG_TOKEN"]

    print("collection:")
    base = fetch_collection(user, token, "collection.xml",
                            "&excludesubtype=boardgameexpansion")
    sleep(SPACING)
    # Expansions are a separate subtype, and they matter: an expansion can
    # change which player counts a base game plays well at.
    exp = fetch_collection(user, token, "expansions.xml",
                           "&subtype=boardgameexpansion")

    ids = owned_ids(base, exp)
    print(f"  {len(ids)} owned items")
    sleep(SPACING)
    fetch_things(ids, token)
    prune(ids)
    print("done — now run: python3 scripts/build.py")


if __name__ == "__main__":
    main()
