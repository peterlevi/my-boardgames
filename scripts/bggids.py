#!/usr/bin/env python3
"""Resolve game *names* to BGG ids, so links can point at the game itself.

    python3 scripts/bggids.py              # resolve names not yet in the cache
    python3 scripts/bggids.py --retry      # also retry names that found nothing

The "people who like this also like" lists come out of the opinion database as
plain names. A name alone can only be turned into a BGG *search* link, which
makes the reader do the last step themselves; BGG's canonical game URL needs the
numeric id. `/xmlapi2/search` is the only way to get from one to the other, and
it takes a single name per request, so the answers are cached in
`data/bgg_ids.json` and a re-run costs nothing for names already seen.

Names that resolve to nothing are cached as null — plenty of the entries are
descriptions rather than titles ("18xx family") and will never resolve, so
retrying them every sync would spend requests on a known-empty answer. `--retry`
asks again for those, for when a game has since been added to BGG.
"""
import json
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus

from common import ROOT, load_creds

CACHE = ROOT / "data" / "bgg_ids.json"
SPACING = 3          # seconds between searches; the endpoint is a light one,
                     # but this is still someone else's server


def norm(name):
    """Fold the differences that stop a title matching itself: case, accents,
    the various dashes, and the ", &"/"and" spelling of a joined title."""
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("–", "-").replace("—", "-").replace(" and ", " & ")
    return "".join(c for c in s if c.isalnum() or c == "&")


def search(name, token, exact):
    url = ("https://boardgamegeek.com/xmlapi2/search?type=boardgame"
           + ("&exact=1" if exact else "")
           + "&query=" + quote_plus(name))
    r = subprocess.run(
        ["curl", "-sS", "--http1.1", "--retry", "2", "--max-time", "45",
         "-H", f"Authorization: Bearer {token}", url],
        capture_output=True, text=True,
    )
    try:
        root = ET.fromstring(r.stdout)
    except ET.ParseError:
        return []
    out = []
    for it in root.findall("item"):
        nm = it.find("name")
        yr = it.find("yearpublished")
        if nm is None:
            continue
        out.append({"id": it.get("id"), "name": nm.get("value"),
                    "year": yr.get("value") if yr is not None else None})
    return out


SEPARATORS = (":", " -", " –", " —", " (")


def subtitled(hit_name, want):
    """True when the hit is the query plus a subtitle — "Caverna" is listed on
    BGG as "Caverna: The Cave Farmers", and people say the short name. The
    separator is required so "Go" cannot swallow "Go Nuts for Donuts"."""
    for sep in SEPARATORS:
        head = hit_name.split(sep)[0]
        if head != hit_name and norm(head) == want:
            return True
    return False


def pick(name, hits):
    """BGG returns search hits in id order, not by relevance, so the oldest
    matching id wins ties — which is usually the original edition rather than a
    reimplementation or a promo pack."""
    if not hits:
        return None
    want = norm(name)
    exact = [h for h in hits if norm(h["name"]) == want]
    if exact:
        return min(exact, key=lambda h: int(h["id"]))
    # Short queries are too ambiguous to match on a prefix alone.
    if len(want) >= 3:
        subs = [h for h in hits if subtitled(h["name"], want)]
        if subs:
            # Lowest id, not shortest name: the original ("Caverna: The Cave
            # Farmers") predates its spin-offs ("Caverna: Cave vs Cave").
            return min(subs, key=lambda h: int(h["id"]))
    return hits[0] if len(hits) == 1 else None


def resolve(names, token, retry=False):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [n for n in names
            if n.lower() not in cache or (retry and cache[n.lower()] is None)]
    if not todo:
        print(f"bgg ids: {len(cache)} cached, nothing new")
        return cache
    print(f"bgg ids: resolving {len(todo)} name(s), "
          f"~{len(todo) * SPACING // 60} min at {SPACING}s apart")
    for i, name in enumerate(todo, 1):
        hit = pick(name, search(name, token, exact=True))
        if not hit:
            time.sleep(SPACING)
            hit = pick(name, search(name, token, exact=False))
        cache[name.lower()] = hit
        print(f"  {i}/{len(todo)} {name} -> " +
              (f"{hit['id']} ({hit['name']})" if hit else "no match"))
        # Write as we go: a long run interrupted keeps everything it paid for.
        CACHE.write_text(json.dumps(cache, indent=1,
                                    ensure_ascii=False, sort_keys=True))
        time.sleep(SPACING)
    return cache


def wanted_names():
    """Every "similar game" name the opinion database mentions."""
    names, d = [], ROOT / "data" / "ai"
    if not d.exists():
        return names
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        for n in rec.get("similar") or []:
            n = (n or "").strip()
            if n and n not in names:
                names.append(n)
    return names


def main():
    names = wanted_names()
    if not names:
        print("no similar-game names to resolve (run scripts/enrich.py first)")
        return
    creds = load_creds()
    cache = resolve(names, creds["BGG_TOKEN"], retry="--retry" in sys.argv)
    found = sum(1 for v in cache.values() if v)
    print(f"{found}/{len(cache)} names resolved -> {CACHE}")


if __name__ == "__main__":
    main()
