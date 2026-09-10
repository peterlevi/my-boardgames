#!/usr/bin/env python3
"""Normalise the cached XML into data/games.json.

    python3 scripts/build.py

Note: in BGG's XML most scalars live in a `value` attribute, not element
text — `<playingtime value="90"/>`, `<averageweight value="3.86"/>`. Reading
them with findtext() silently yields empty strings.
"""
import glob
import json
import xml.etree.ElementTree as ET

from common import RAW, ROOT


def attr(node, tag):
    if node is None:
        return None
    e = node.find(tag)
    return e.get("value") if e is not None else None


def parse_item(it):
    name = next((n.get("value") for n in it.findall("name")
                 if n.get("type") == "primary"), "")
    st = it.find("statistics/ratings")

    rank = None
    if st is not None:
        for r in st.findall("ranks/rank"):
            if r.get("name") == "boardgame":
                v = r.get("value")
                rank = int(v) if v and v.isdigit() else None

    # suggested_numplayers poll -> {"4": {"Best": n, "Recommended": n, ...}}
    poll = {}
    for p in it.findall("poll"):
        if p.get("name") != "suggested_numplayers":
            continue
        for res in p.findall("results"):
            poll[res.get("numplayers")] = {
                r.get("value"): int(r.get("numvotes")) for r in res.findall("result")
            }

    def num(v, cast=float):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    return dict(
        id=it.get("id"), name=name, year=num(attr(it, "yearpublished"), int),
        rank=rank,
        weight=num(attr(st, "averageweight")), average=num(attr(st, "average")),
        minplayers=num(attr(it, "minplayers"), int),
        maxplayers=num(attr(it, "maxplayers"), int),
        playingtime=num(attr(it, "playingtime"), int),
        minplaytime=num(attr(it, "minplaytime"), int),
        maxplaytime=num(attr(it, "maxplaytime"), int),
        poll=poll,
    )


def main():
    games = []
    for f in sorted(glob.glob(str(RAW / "thing_*.xml"))):
        games += [parse_item(it) for it in ET.parse(f).getroot().findall("item")]
    out = ROOT / "data" / "games.json"
    out.write_text(json.dumps(games, indent=1, ensure_ascii=False))
    print(f"{len(games)} games -> {out}")


if __name__ == "__main__":
    main()
