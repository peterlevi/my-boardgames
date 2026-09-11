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
import json
import re
import xml.etree.ElementTree as ET

import interaction
import traits
from common import RAW, ROOT


def attr(node, tag):
    if node is None:
        return None
    e = node.find(tag)
    return e.get("value") if e is not None else None


def links(it, kind):
    return [l.get("value") for l in it.findall("link") if l.get("type") == kind]


def clean_description(raw):
    """BGG descriptions arrive with HTML entities and literal &#10; newlines."""
    import html as htmllib
    text = htmllib.unescape(raw).replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    families = links(it, "boardgamefamily")
    designers = links(it, "boardgamedesigner")
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
        geek=num(attr(st, "bayesaverage")),
        # How many people rated it: BGG calls this "usersrated" and labels it
        # "Ratings" on a game page. Unlike the poll votes it does not depend on
        # a player count.
        ratings=num(attr(st, "usersrated"), int),
        owners=num(attr(st, "owned"), int),
        description=clean_description(it.findtext("description") or ""),
        minplayers=num(attr(it, "minplayers"), int),
        maxplayers=num(attr(it, "maxplayers"), int),
        playingtime=num(attr(it, "playingtime"), int),
        minplaytime=num(attr(it, "minplaytime"), int),
        maxplaytime=num(attr(it, "maxplaytime"), int),
        mechanics=mechanics, categories=categories, families=families,
        designers=designers, traits=traits.of(mechanics),
        interaction=level, interaction_shared=shared,
        poll=poll,
    )


def load_ai():
    """The optional opinion database from scripts/enrich.py. Absent is fine —
    every field it feeds is additive."""
    out = {}
    d = ROOT / "data" / "ai"
    if not d.exists():
        return out
    for f in d.glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
    return out


def ids_in(name):
    """Object ids listed in one of the collection exports, in file order."""
    f = RAW / name
    if not f.exists():
        return []
    return [it.get("objectid") for it in ET.parse(f).getroot().findall("item")]


def collection_stats():
    """Play counts and the owner's own rating both ride along with the
    collection export (`stats=1`), so neither costs an extra API call. An
    unrated game carries value="N/A"."""
    plays, mine = {}, {}
    for name in ("collection.xml", "expansions.xml"):
        f = RAW / name
        if not f.exists():
            continue
        for it in ET.parse(f).getroot().findall("item"):
            oid = it.get("objectid")
            plays[oid] = int(it.findtext("numplays") or 0)
            rating = it.find("stats/rating")
            v = rating.get("value") if rating is not None else None
            if v and v != "N/A":
                try:
                    mine[oid] = float(v)
                except ValueError:
                    pass
    return plays, mine


def main():
    # The collection exports say what is owned and which of it is an expansion;
    # the per-id detail files supply everything else. Driving the build from the
    # collection means a game you no longer own simply stops appearing.
    base_ids = ids_in("collection.xml")
    exp_ids = ids_in("expansions.xml")

    games, missing = [], []
    for oid in base_ids + exp_ids:
        f = RAW / "things" / f"{oid}.xml"
        if not f.exists():
            missing.append(oid)
            continue
        for it in ET.parse(f).getroot().findall("item"):
            games.append(parse_item(it, oid in exp_ids))
    if missing:
        print(f"warning: {len(missing)} owned item(s) have no cached detail — "
              f"run scripts/fetch.py")

    plays, mine = collection_stats()
    ai = load_ai()
    for g in games:
        g["ai"] = ai.get(g["id"])
        g["plays"] = plays.get(g["id"], 0)
        g["my_rating"] = mine.get(g["id"])

    out = ROOT / "data" / "games.json"
    out.write_text(json.dumps(games, indent=1, ensure_ascii=False))
    base = sum(1 for g in games if not g["is_expansion"])
    print(f"{base} games + {len(games) - base} expansions -> {out}")


if __name__ == "__main__":
    main()
