#!/usr/bin/env python3
"""Normalise the cached XML into data/games.json.

    python3 scripts/build.py

Note: in BGG's XML most scalars live in a `value` attribute, not element
text — `<playingtime value="90"/>`, `<averageweight value="3.86"/>`. Reading
them with findtext() silently yields empty strings.

Expansions are parsed too (from exp_*.xml) and carry `expands`: the ids of the
base games they attach to, via the inbound boardgameexpansion link. The report
uses that to let an expansion's player-count poll speak for its base game.
"""
import glob
import json
import xml.etree.ElementTree as ET

import interaction
from common import RAW, ROOT, load_exclusions


def attr(node, tag):
    if node is None:
        return None
    e = node.find(tag)
    return e.get("value") if e is not None else None


def links(it, kind):
    return [l.get("value") for l in it.findall("link") if l.get("type") == kind]


def parse_item(it, is_expansion=False):
    name = next((n.get("value") for n in it.findall("name")
                 if n.get("type") == "primary"), "")
    st = it.find("statistics/ratings")

    rank = None
    if st is not None:
        for r in st.findall("ranks/rank"):
            if r.get("name") == "boardgame":
                v = r.get("value")
                rank = int(v) if v and v.isdigit() else None

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

    mechanics = links(it, "boardgamemechanic")
    categories = links(it, "boardgamecategory")
    # On an expansion's page the boardgameexpansion link is inbound and names
    # the base game; on a base game it is outbound and names the expansions.
    expands = [l.get("id") for l in it.findall("link")
               if l.get("type") == "boardgameexpansion" and l.get("inbound")]

    level, shared = interaction.classify(name, mechanics, categories)
    return dict(
        id=it.get("id"), name=name, year=num(attr(it, "yearpublished"), int),
        rank=rank, is_expansion=is_expansion, expands=expands,
        thumbnail=(it.findtext("thumbnail") or "").strip() or None,
        weight=num(attr(st, "averageweight")), average=num(attr(st, "average")),
        minplayers=num(attr(it, "minplayers"), int),
        maxplayers=num(attr(it, "maxplayers"), int),
        playingtime=num(attr(it, "playingtime"), int),
        minplaytime=num(attr(it, "minplaytime"), int),
        maxplaytime=num(attr(it, "maxplaytime"), int),
        mechanics=mechanics, categories=categories,
        interaction=level, interaction_shared=shared,
        poll=poll,
    )


def plays_by_id():
    """Play counts come free with the collection export (`stats=1`), so this
    costs no extra API calls."""
    plays = {}
    for name in ("collection.xml", "expansions.xml"):
        f = RAW / name
        if not f.exists():
            continue
        for it in ET.parse(f).getroot().findall("item"):
            plays[it.get("objectid")] = int(it.findtext("numplays") or 0)
    return plays


def main():
    games = []
    for pattern, is_exp in (("thing_*.xml", False), ("exp_*.xml", True)):
        for f in sorted(glob.glob(str(RAW / pattern))):
            games += [parse_item(it, is_exp)
                      for it in ET.parse(f).getroot().findall("item")]

    salads = load_exclusions("point-salads.txt")
    plays = plays_by_id()
    for g in games:
        g["point_salad"] = g["name"] in salads
        g["plays"] = plays.get(g["id"], 0)

    out = ROOT / "data" / "games.json"
    out.write_text(json.dumps(games, indent=1, ensure_ascii=False))
    base = sum(1 for g in games if not g["is_expansion"])
    print(f"{base} games + {len(games) - base} expansions -> {out}")


if __name__ == "__main__":
    main()
