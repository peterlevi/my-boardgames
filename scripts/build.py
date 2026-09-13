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
import os
import re
import sys
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
    # BGG's other titles for the same game — foreign editions, mostly. Never
    # shown, but worth searching: somebody looking for Les Chateaux de
    # Bourgogne should find The Castles of Burgundy.
    alt = [n.get("value") for n in it.findall("name")
           if n.get("type") == "alternate" and n.get("value")]
    st = it.find("statistics/ratings")

    rank = None
    types = []
    if st is not None:
        for r in st.findall("ranks/rank"):
            if r.get("name") == "boardgame":
                v = r.get("value")
                rank = int(v) if v and v.isdigit() else None
            elif r.get("type") == "family":
                # BGG's own sections — Strategy, Family, Thematic and so on.
                # A game is listed in one only if it is ranked there.
                label = (r.get("friendlyname") or "").replace(" Rank", "").strip()
                if label and r.get("value", "").isdigit():
                    types.append(label)

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
    # BGG lists every edition's publisher — twenty of them for a popular game,
    # mostly foreign-language reprints — with the original first. The first
    # few are the ones anybody means.
    publishers = links(it, "boardgamepublisher")[:3]
    # Their BGG ids come free with the same links, and are what a designer's
    # own BGG page is addressed by.
    designer_ids = {l.get("value"): l.get("id") for l in it.findall("link")
                    if l.get("type") == "boardgamedesigner"}
    # BGG returns a mixed bag; instructional videos are the teaching ones, and
    # English first since that is what this collection wants.
    videos = []
    for v in it.findall("videos/video"):
        if v.get("category") != "instructional":
            continue
        videos.append({"title": v.get("title"), "link": v.get("link"),
                       "who": v.get("username"),
                       "lang": v.get("language")})
    videos.sort(key=lambda v: v["lang"] != "English")
    # On an expansion's page the boardgameexpansion link is inbound and names
    # the base game; on a base game it is outbound and names the expansions.
    expands = [l.get("id") for l in it.findall("link")
               if l.get("type") == "boardgameexpansion" and l.get("inbound")]

    level, shared = interaction.classify(name, mechanics, categories)
    return dict(
        id=it.get("id"), name=name, alt_names=alt,
        year=num(attr(it, "yearpublished"), int),
        rank=rank, types=types, is_expansion=is_expansion, expands=expands,
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
        designers=designers, designer_ids=designer_ids,
        publishers=publishers,
        traits=traits.of(mechanics), videos=videos[:3],
        image=(it.findtext("image") or "").strip() or None,
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


def load_plays():
    """When each game was last played, from scripts/plays.py. Absent is fine."""
    f = ROOT / "data" / "plays.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:  # noqa: BLE001
        return {}


def load_bgg_ids():
    """Name -> BGG id for games outside the collection, from scripts/bggids.py.
    Absent is fine: a name without an id falls back to a BGG search link."""
    f = ROOT / "data" / "bgg_ids.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:  # noqa: BLE001
        return {}


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
    plays, mine, acquired, edited = {}, {}, {}, {}
    for name in ("collection.xml", "expansions.xml"):
        f = RAW / name
        if not f.exists():
            continue
        for it in ET.parse(f).getroot().findall("item"):
            oid = it.get("objectid")
            plays[oid] = int(it.findtext("numplays") or 0)
            # Only present when BGG chooses to return private fields; it does
            # not for an API token, so this is usually empty.
            # Present only if BGG ever starts returning private fields to an
            # API token; it does not today.
            priv = it.find("privateinfo")
            if priv is not None and priv.get("acquisitiondate"):
                acquired[oid] = priv.get("acquisitiondate")[:10]
            # When the collection entry itself last changed. Not the date you
            # got the game — an edited entry moves — so it is called what it
            # is rather than standing in for something else.
            st = it.find("status")
            if st is not None and st.get("lastmodified"):
                edited[oid] = st.get("lastmodified")[:10]
            rating = it.find("stats/rating")
            v = rating.get("value") if rating is not None else None
            if v and v != "N/A":
                try:
                    mine[oid] = float(v)
                except ValueError:
                    pass
    return plays, mine, acquired, edited


def note_owner():
    """Record whose collection this is, so the report can say so even where the
    credentials are not — in CI, or from a checkout without them. A BGG
    username is public; nothing secret goes in here."""
    name = os.environ.get("BGG_USERNAME")
    f = ROOT / "credentials.env"
    if not name and f.exists():
        for line in f.read_text().splitlines():
            if line.strip().startswith("BGG_USERNAME"):
                name = line.split("=", 1)[-1].strip()
    if not name:
        return
    meta = ROOT / "data" / "meta.json"
    meta.write_text(json.dumps({"owner": name}, indent=1) + "\n")


def csv_rows():
    """The owned rows of a BGG collection CSV export, if one is present."""
    f = ROOT / "data" / "collection.csv"
    if not f.exists():
        return []
    import csv
    with f.open(newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("own") == "1"]


def counts_from(value):
    """"3,4,5" -> [3, 4, 5]. BGG writes the recommendation summary this way."""
    out = []
    for part in (value or "").split(","):
        part = part.strip().rstrip("+")
        if part.isdigit():
            out.append(int(part))
    return out


def games_from_csv(rows):
    """Build the collection from the CSV export alone, for people who would
    rather not hand the tool an API token.

    The export carries the numbers — rank, ratings, weight, times, play counts
    — and BGG's own summary of which player counts are best and which are
    recommended, which is what the player-count filters actually need. What it
    cannot carry is everything the /thing endpoint knows: mechanics,
    categories, designers, the full poll with its percentages, descriptions
    and images. Those parts of the report simply stay empty.
    """
    def num(v, cast=float):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    games = []
    for r in rows:
        rank = num(r.get("rank"), int)
        weight = num(r.get("avgweight"))
        games.append(dict(
            id=r.get("objectid"), name=r.get("objectname") or "",
            year=num(r.get("yearpublished"), int),
            rank=rank if rank else None,
            types=[], weight=round(weight, 4) if weight else None,
            average=num(r.get("average")), geek=num(r.get("baverage")),
            ratings=None, owners=num(r.get("numowned"), int),
            minplayers=num(r.get("minplayers"), int) or 0,
            maxplayers=num(r.get("maxplayers"), int) or 0,
            minplaytime=num(r.get("minplaytime"), int) or 0,
            maxplaytime=num(r.get("maxplaytime"), int) or 0,
            mechanics=[], categories=[], families=[], designers=[],
            publishers=[],
            designer_ids={}, traits=[], videos=[], image=None, thumbnail=None,
            description=None,
            interaction=None, interaction_shared=None,
            poll={}, best_at=counts_from(r.get("bggbestplayers")),
            rec_at=counts_from(r.get("bggrecplayers")),
            is_expansion=(r.get("itemtype") == "expansion"), expands=None,
            source="csv",
        ))
    return games


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

    rows = csv_rows()
    if not games and rows:
        # No API cache at all: build what the CSV export can support.
        games = games_from_csv(rows)
        print(f"no cached BGG data — building from data/collection.csv "
              f"({len(games)} items, no mechanics, poll percentages or images)")

    plays, mine, _acquired, edited = collection_stats()
    csv_plays, csv_rating = {}, {}
    for r in rows:
        oid = r.get("objectid")
        try:
            csv_plays[oid] = int(r.get("numplays") or 0)
        except ValueError:
            pass
        try:
            v = float(r.get("rating") or 0)
            if v:
                csv_rating[oid] = v
        except ValueError:
            pass
    played = load_plays()
    ai = load_ai()
    bgg_ids = load_bgg_ids()
    for g in games:
        g["ai"] = ai.get(g["id"])
        if g["ai"] and g["ai"].get("similar"):
            # Carry the id alongside each name so the report can link straight
            # at the game; `id` stays None when the name never resolved.
            g["ai"]["similar"] = [
                {"name": n, "id": (bgg_ids.get((n or "").strip().lower()) or {}).get("id")}
                for n in g["ai"]["similar"]
            ]
        g["plays"] = plays.get(g["id"], csv_plays.get(g["id"], 0))
        g["my_rating"] = mine.get(g["id"]) or csv_rating.get(g["id"])
        # Nothing private goes in here: data/games.json is committed and
        # published. Price paid and acquisition date are read straight from
        # the gitignored CSV by report.py, at render time.
        g["edited"] = edited.get(g["id"])
        g["last_played"] = (played.get(g["id"]) or {}).get("last") or None

    note_owner()
    out = ROOT / "data" / "games.json"
    out.write_text(json.dumps(games, indent=1, ensure_ascii=False))
    base = sum(1 for g in games if not g["is_expansion"])
    print(f"{base} games + {len(games) - base} expansions -> {out}")


if __name__ == "__main__":
    main()
