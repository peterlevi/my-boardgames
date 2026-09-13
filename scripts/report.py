#!/usr/bin/env python3
"""Render the whole collection as a standalone, filterable HTML report.

    python3 scripts/report.py -o reports/collection.html
    python3 scripts/report.py --players 4 --mode best -o reports/best-at-4.html

Unlike query.py this does not filter server-side: every owned game is embedded
in the page and all filtering happens in the browser, so one file answers any
question. The CLI flags only choose which filters the page *opens* with.

By default thumbnails are inlined as data URIs from data/thumbs/, making the
file completely self-contained — Slack renders the page but blocks hotlinked
images, so a report meant to travel has to carry its own. Run
`python3 scripts/thumbs.py` first to populate that cache. Pass --link-thumbs
for a ~10x smaller file that hotlinks to BGG's CDN instead and therefore needs
internet.
"""
import argparse
import base64
import datetime as dt
import json
import sys
import unicodedata
import os
import re
import subprocess
from pathlib import Path

from common import ROOT, load_games, playtime, load_overrides
from scoring import (SALAD_LABEL, SALAD_PILL, SALAD_SHORT, WIN_LABEL,
                     WIN_ORDER, WIN_SHORT, salad, salad_score, score_sort, score_text,
                     win, wins)

THUMBS = ROOT / "data" / "thumbs"

HERE = Path(__file__).resolve().parent


def thumb_uri(game):
    """A base64 data URI for the cached, downscaled thumbnail, or None."""
    f = THUMBS / f'{game["id"]}.jpg'
    if not f.exists():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


# Everything the one filter field can match, in the order the list shows them.
# Names can collide across kinds, so a tag is keyed by (kind, name).
TAG_KINDS = [
    ("trait", "traits", "trait"),
    ("win", "win_conditions", "win condition"),
    ("ixkind", "interaction_kinds", "interaction kind"),
    ("category", "categories", "cat"),
    ("mechanism", "mechanics", "mech"),
    ("designer", "designers", "designer"),
    ("family", "families", "family"),
    ("type", "types", "type"),
]

# BGG families are a long tail of one-offs and housekeeping; anything appearing
# once is noise in a picker this size.
FAMILY_MIN = 2
FAMILY_SKIP = ("Admin:", "Digital Implementations", "Crowdfunding")


def annotate(games):
    """Hang the two derived vocabularies on each game so they can be indexed
    and filtered like any BGG property.

    Neither is a list BGG gives us: how a game is won is computed by
    scoring.py from the facts the opinion pass reports, and the kind of
    interaction by interaction.py from the sentence it writes. Both are
    already computed for the columns; putting them in the property picker
    costs nothing further and means one field filters everything a game is.
    """
    by_id = {g["id"]: g for g in games}
    for g in games:
        facts = (g.get("ai") or {}).get("scoring") or {}
        g["win_conditions"] = [WIN_LABEL.get(w, w) for w in wins(facts)]
        g["interaction_kinds"] = interaction_kinds(g, by_id)


def tag_index(games):
    """Every filterable property in the collection — trait, category,
    mechanic, designer, family — with counts and, where useful, a description.
    Each game carries indices into this list; the names would otherwise repeat
    thousands of times in the payload."""
    import traits as traits_mod

    desc = load_overrides("tag-descriptions.txt")
    desc.update(traits_mod.DESCRIPTIONS)

    counts = {}
    for g in games:
        for kind, field, _ in TAG_KINDS:
            for t in g.get(field, []):
                counts[(kind, t)] = counts.get((kind, t), 0) + 1

    order = {k: i for i, (k, _, _) in enumerate(TAG_KINDS)}
    label = {k: lab for k, _, lab in TAG_KINDS}

    def keep(key):
        kind, name = key
        if kind != "family":
            return True
        return counts[key] >= FAMILY_MIN and not name.startswith(FAMILY_SKIP)

    keys = sorted((k for k in counts if keep(k)),
                  key=lambda k: (order[k[0]], k[1]))
    idx = {k: i for i, k in enumerate(keys)}

    def describe_tag(kind, name):
        """A description for this tag, most specific first.

        The same word means different things in different vocabularies: BGG's
        *mechanic* Race is "first to the end of a track wins", while the
        *interaction kind* Race is about everyone pushing for one finish. A
        bare name lookup gave both the first wording, which reads as a win
        condition filed under interaction. A `kind:Name` entry wins where one
        exists, and the bare name still covers everything else.
        """
        return (desc.get(f"{label[kind]}:{name}")
                or desc.get(name, ""))

    tags = [{"n": name, "k": label[kind], "c": counts[(kind, name)],
             "d": describe_tag(kind, name)} for kind, name in keys]
    return tags, idx


def interaction_kinds(g, by_id):
    """The kinds of interaction a game shows, most particular first.

    An expansion with no opinion entry of its own borrows its base game's:
    Ra: Traders interacts the way Ra does, and a blank there would be a hole
    in the filter rather than a fact about the game.
    """
    import interaction as ix_mod

    def call(game):
        ai = game.get("ai") or {}
        ix = ai.get("interaction") or {}
        return ix_mod.classify_kinds(ix.get("kind"),
                                     game.get("mechanics") or [],
                                     game.get("categories") or [],
                                     game.get("interaction"))

    kinds = call(g)
    if kinds:
        return kinds
    for base in g.get("expands") or []:
        if base in by_id:
            kinds = call(by_id[base])
            if kinds:
                return kinds
    return []


def compact(games, tag_idx, inline=True, private=None):
    """Trim to what the page actually renders, and precompute per-game values
    the browser would otherwise recompute on every keystroke."""
    out, missing = [], 0
    by_id = {g["id"]: g for g in games}
    for g in games:
        thumb = g["thumbnail"]
        if inline:
            thumb = thumb_uri(g)
            if thumb is None:
                missing += 1
                thumb = g["thumbnail"]
        poll = {}
        for n, d in g["poll"].items():
            b, r, x = (d.get("Best", 0), d.get("Recommended", 0),
                       d.get("Not Recommended", 0))
            if b + r + x:
                poll[n] = [b, r, x]
        out.append({
            "id": g["id"], "n": g["name"], "y": g["year"], "rk": g["rank"],
            "alt": g.get("alt_names") or [],
            "th": thumb, "w": g["weight"], "av": g["average"],
            "gk": g["geek"], "my": g["my_rating"],
            "tmin": g["minplaytime"], "tmax": g["maxplaytime"],
            "pmin": g["minplayers"], "pmax": g["maxplayers"],
            "pl": g["plays"], "ds": g["designers"],
            "dsid": g.get("designer_ids") or {},
            "pb": g.get("publishers") or [],
            "lp": g.get("last_played"),
            "ed": g.get("edited"),
            "rt": g["ratings"], "ow": g["owners"],
            "wv": g.get("weight_votes"),
            "de": (g["description"] or "")[:900],
            "mn": g["minplayers"], "mx": g["maxplayers"],
            "ai": trim_ai(g.get("ai")),
            "img": g.get("image"), "vid": g.get("videos") or [],
            "gal": load_gallery(g["id"], g.get("image")),
            "ix": g["interaction"], "kinds": interaction_kinds(g, by_id),
            "exp": 1 if g["is_expansion"] else 0,
            "of": g["expands"] or [], "t": playtime(g),
            "top": max((v[0] for v in poll.values()), default=0),
            "bestAt": g.get("best_at") or [],
            "recAt": g.get("rec_at") or [],
            "poll": poll,
            **(private or {}).get(g["id"], {}),
            "tg": sorted(tag_idx[(kind, t)]
                         for kind, field, _ in TAG_KINDS
                         for t in set(g.get(field, []))
                         if (kind, t) in tag_idx),
        })
    if missing:
        print(f"warning: {missing} thumbnails not cached, hotlinked instead — "
              f"run scripts/thumbs.py")
    return out


RATING_COLORS = ["#a03530", "#a03530", "#b3414c", "#b94a75", "#a9518f",
                 "#8560a4", "#5b71ac", "#3778a8", "#3f8a5f", "#2d7a4d",
                 "#1d6b40"]


EM_DASH = "\u2014"

# More interaction reads as the better end of the ramp.
IX_PILL = {"High": "p3", "Medium": "p2", "Low": "p1"}

# Bands for the two BGG numbers that are easier to filter by name than by
# range. Both tables are shipped into the page as JSON rather than written out
# a second time in JavaScript, so the filter, the pill and the column cannot
# drift apart. `lt` is the exclusive upper edge; the last band has none.
#
# Weight borrows BGG's vocabulary but cuts on the whole numbers. Their Game
# Weight poll names five points on the 1-5 scale \u2014 Light, Medium Light,
# Medium, Medium Heavy, Heavy \u2014 and the API returns only the number, so the
# naming has to happen here.
#
# The cuts were the midpoints between those five anchors at first, which is
# how BGG's own pages round a weight to a word. It reads wrong in a table:
# 3.86 and 4.36 both round to 4 and so both came out "Medium heavy", and a
# 4.36 game that is plainly heavy sat under the same label as one well under
# 4. Whole numbers are what a reader assumes a 1-5 scale means \u2014 four and up
# is heavy \u2014 so that is what these are, at the cost of dropping one of BGG's
# five names.
WEIGHT_BANDS = [
    {"k": "light", "n": "Light", "lt": 1.5, "pill": "p3", "bar": "wt1"},
    {"k": "medlight", "n": "Medium light", "lt": 2.5, "pill": "p2", "bar": "wt2"},
    {"k": "medium", "n": "Medium", "lt": 3.5, "pill": "p2", "bar": "wt2"},
    {"k": "medheavy", "n": "Heavy", "lt": 4.5, "pill": "p1", "bar": "wt3"},
    {"k": "heavy", "n": "Extreme", "lt": None, "pill": "pw", "bar": "wt4"},
]

# Time is banded on the *upper* bound, because the question at a game night is
# how long this could run, not how fast it could be over. "Very long" starts
# at the four hours BGG itself prints on the box.
# What the column pill says about a game's length, by its *upper* bound: at a
# game night the question is how long this could run, not how quickly it could
# be over.
#
# These are words, not numbers, and that is the point. The pill used to read
# "4 hours+" for a game listed 40-200, which is a claim about the game the
# game does not support — its top end passes four hours, but it can be over in
# forty minutes. "Extreme" says where it sits without promising a figure, and
# it frees this grouping from the filter's stops, which are finer and answer a
# different question.
TIME_BANDS = [
    {"k": "vshort", "n": "Very short", "lt": 30, "pill": "p3", "bar": "wt1"},
    {"k": "short", "n": "Short", "lt": 46, "pill": "p3", "bar": "wt1"},
    {"k": "medium", "n": "Medium", "lt": 91, "pill": "p1", "bar": "wt2"},
    {"k": "long", "n": "Long", "lt": 121, "pill": "p2", "bar": "wt3"},
    {"k": "vlong", "n": "Very long", "lt": 181, "pill": "pw", "bar": "wt4"},
    {"k": "extreme", "n": "Extreme", "lt": None, "pill": "pw", "bar": "wt4"},
]

# Where a time bar runs out. Four hours is the top band's floor, so anything
# at or past it fills the track.
TIME_FULL = 240


def scales():
    """The axes the four range filters run over, shipped to the page.

    Each is a list of **stops**: a label, the stretch of the underlying number
    it names, and the value that anchors it on the track. The number is what
    is actually filtered on — weight 1-5, time in minutes, point salad its
    0-100 score — so the filter keeps the precision the number has while
    reading in the vocabulary the columns use.

    The stops are drawn *evenly spaced* however uneven their values are: a
    scale whose steps are 30, 30, 30, 30, 60 and 60 minutes is a scale you
    read by its labels, not by the gaps between them, and spacing it by value
    crams the short end into a third of the track. The page maps position to
    value piecewise, so dragging still lands on real numbers in between.
    """
    def stops(rows):
        """(name, low, high) per stop, plus an optional short name for the
        collapsed caption where the full one is a phrase."""
        out = []
        for r in rows:
            st = {"n": r[0], "lo": r[1], "hi": r[2], "v": r[2]}
            if len(r) > 3:
                st["s"] = r[3]
            out.append(st)
        return out

    def weight_stops():
        """The weight filter's stops are the column's own bands.

        They used to be written out a second time here, and they drifted: the
        pills moved to BGG's cuts at 1.5/2.5/3.5/4.5 and the filter stayed at
        2/3/3.5/4, so asking for "Medium light" filtered a different set of
        games than the column was calling Medium light. One band table, read
        twice.
        """
        rows, lo = [], 1
        for b in WEIGHT_BANDS:
            hi = b["lt"] if b["lt"] is not None else 5
            rows.append((b["n"], lo, hi))
            lo = hi
        return rows

    import scoring
    sb = scoring.SALAD_BANDS
    return {
        # A game is Low, Medium or High and nothing in between, so this one
        # snaps to its stops.
        # `brief` is how the collapsed control says what is picked, with nine
        # filters sharing one row:
        #   "level" — name the stops, always ("Med", "Med–High").
        #   "band"  — name one stop, but give a span as numbers: the band
        #             names here are phrases and two of them will not fit.
        #   "num"   — always the numbers being filtered on. Weight and time
        #             are read as quantities rather than as words, and "Light"
        #             does not say where it stops while "≤ 1.5" does.
        # The numeric forms say an end that reaches the edge of the scale as
        # "≤ x" or "x+" rather than naming a stop nobody chose.
        "ix": {"min": 0, "max": 2, "step": 1, "unit": "", "snap": True,
               "brief": "level",
               "stops": stops([("Low", 0, 0, "Low"), ("Medium", 1, 1, "Med"),
                               ("High", 2, 2, "High")])},
        # Weight is the one continuous axis, so its bands meet at the edge
        # rather than a step below it: writing 3.99 for "just under 4" leaves
        # every weight between 3.99 and 4 in no band at all, and there are
        # four such games. `hiExclusive` says the top of a band belongs to the
        # next one — except for the last, which owns its own ceiling.
        # `edgesMeet` says a band starts where the one below it ends, so
        # reading a stored range back finds the band that *contains* the low
        # bound rather than the one that ends at it. `hiExclusive` is about
        # filtering rather than reading: a game weighing exactly 3.5 is Heavy,
        # not Medium, so the top of a band is not in it.
        "wband": {"min": 1, "max": 5, "step": 0.01, "unit": "",
                  "edgesMeet": True, "hiExclusive": True, "brief": "num",
                  "stops": stops(weight_stops())},
        "salad": {"min": 0, "max": 100, "step": 1, "unit": "%",
                  "brief": "band",
                  "stops": stops([("No", 0, sb[0] - 1),
                                  ("A touch", sb[0], sb[1] - 1),
                                  ("Quite a lot", sb[1], sb[2] - 1),
                                  ("Point salad", sb[2], 100)])},
        # Time's stops are not the column's bands: the bands name a length in
        # one word, while the filter wants the lengths a game night is
        # actually planned around. Both ends are open — the lowest stop means
        # "no lower bound", the highest "no upper bound" — so a wide-open
        # slider cannot drop the 480-minute games off a 240-minute axis.
        #
        # Each stop is named for the stretch it covers rather than for the
        # time it runs up to, and the boundary belongs to both neighbours: a
        # 90-minute game is in "60–90 min" and in "90–120 min" both. That is
        # the useful reading for a filter — you are asking "could we fit this
        # in before ten" — and unlike the weight column there is no pill here
        # that has to pick one band for the game.
        "tband": {"min": 0, "max": 240, "step": 5, "unit": " min",
                  "openBottom": True, "openTop": True, "brief": "num",
                  "edgesMeet": True, "spanNames": True,
                  "stops": stops([("≤ 15 min", 0, 15),
                                  ("15–30 min", 15, 30),
                                  ("30–45 min", 30, 45),
                                  ("45–60 min", 45, 60),
                                  ("60–90 min", 60, 90),
                                  ("90–120 min", 90, 120),
                                  ("120–180 min", 120, 180),
                                  ("≥ 180 min", 180, 240)])},
    }


def ix_kinds():
    import interaction as ix_mod
    return list(ix_mod.KIND_NAMES)


def band_of(bands, v):
    """The band a value falls in, or None when there is no value to band.

    Mirrored by bandOf() in the page script, over the same table.
    """
    if not v:
        return None
    for b in bands:
        if b["lt"] is None or v < b["lt"]:
            return b
    return bands[-1]



def esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def stats_at(g, n):
    """Mirror of statsAt() in the page script."""
    d = g["poll"].get(str(n))
    if not d:
        # A CSV-built collection has no poll, only BGG's summary of which
        # counts are best and which are recommended — enough for the verdict,
        # not enough for a percentage.
        best, rec = g.get("bestAt") or [], g.get("recAt") or []
        if n in best or n in rec:
            return {"best": None, "total": None, "bestPct": None, "appr": None,
                    "isBest": n in best, "good": n in rec or n in best}
        return None
    b, r, x = d
    total = b + r + x
    if not total:
        return None
    return {"best": b, "total": total, "bestPct": 100.0 * b / total,
            "appr": 100.0 * (b + r) / total,
            "isBest": b == g["top"] and b > 0}


def in_range_at(g, n):
    """Whether the box says this game takes n players at all.

    BGG polls every count from one upwards, so a poll entry at n is no
    evidence a game plays there: Catan's 1-player row carries 1,565 votes, of
    which 1,560 say "not recommended". Asking only whether votes exist made
    "Plays at 1p" true for essentially the whole collection. Mirrored by
    inRangeAt() in the page script.
    """
    if not n:
        return True
    lo, hi = g.get("mn") or g.get("minplayers") or 0, \
        g.get("mx") or g.get("maxplayers") or 0
    if not lo and not hi:
        return True
    return (not lo or n >= lo) and (not hi or n <= hi)


def stands_at(g, s, n, mode):
    """Whether a game answers for itself at n: in range, and passing the rule."""
    return in_range_at(g, n) and qualifies(s, mode)


def qualifies(s, mode):
    if not s:
        return False
    if mode == "best":
        return s["isBest"]
    if mode == "good":
        if s["bestPct"] is None:
            return bool(s.get("good"))
        return s["isBest"] or s["bestPct"] >= 50
    return True


def reading(g, n, by_base, fold, mode):
    s = stats_at(g, n)
    if not fold or g["exp"] or stands_at(g, s, n, mode):
        return s, None
    for e in by_base.get(g["id"], []):
        cand = stats_at(e, n)
        if not cand:
            continue
        # The expansion has to reach the count itself, not merely have been
        # polled at it.
        if stands_at(e, cand, n, mode):
            return cand, e["n"]
    return s, None


def meter_class(pct):
    """Strong to weak, so a column of percentages reads by colour."""
    if pct >= 85:
        return "m4"
    if pct >= 70:
        return "m3"
    if pct >= 50:
        return "m2"
    return "m1"


def band_cell(band, pct, text, title):
    """A banded number in the one cell that can show it three ways.

    Weight reads faster as a colour than as a number, and "Medium light" reads
    faster still than 3.86 — but which of those you want depends on what you
    are doing with the table that minute, not on which column you once picked.
    So the cell carries all of it: the pill, the figure, and the bar. One
    setting in the picker decides which parts are on screen, and it decides it
    for every column of this kind at once.

    This used to be three columns per axis in the picker — "band and number",
    "band only", "number only" — which is twelve menu entries to say four
    things, and a reader who wanted numbers everywhere had to find and retick
    four of them. The renderings were never independent of each other.
    """
    if not band:
        return EM_DASH
    pill = f'<span class="tag {band["pill"]}">{esc(band["n"])}</span>'
    return pill_bar(pill, [meter(pct, band["bar"], text=text)],
                    title=title, top=text)


def weight_cell(w):
    b = band_of(WEIGHT_BANDS, w)
    if not b:
        return EM_DASH
    return band_cell(b, w / 5 * 100, f"{w:.2f}",
                     f'Weight {w:.2f} of 5 — {b["n"]}')


def time_cell(g):
    """Time bands read the *upper* bound: at a game night the question is how
    long this could run, not how quickly it could be over."""
    hi = g["tmax"]
    b = band_of(TIME_BANDS, hi)
    if not b:
        return EM_DASH
    return band_cell(b, min(hi / TIME_FULL * 100, 100), g["t"],
                     f'{g["t"]} minutes — {b["n"]}')


def meter(pct, cls=None, label=None, text=None):
    """One measurement with its bar — the unit every pill+bar column is built
    from, and the same markup the weight column has always used.

    `pct` positions the bar on a 0-100 track. `text` is what to print beside
    it when the figure is not that percentage: weight says "3.86 of 5" on a
    1-5 scale and time says "60–90" minutes, but both still read as a bar
    filled some fraction of the way along. `label` names the reading, which
    only matters where a column carries two of them and the header can no
    longer say which is which.
    """
    if pct is None:
        return f'<span class="bar"><span class="pct">{EM_DASH}</span></span>'
    lab = f'<b>{esc(label)}</b>' if label else ""
    figure = esc(text) if text is not None else f"{pct:.0f}%"
    # Label, then the bar, then the figure: the bar is the thing being
    # scanned down a column and the number is the footnote to it, so the
    # number sits small and right-aligned at the cell's edge rather than
    # above the bar in full size.
    return (f'<span class="bar">{lab}'
            f'<span class="track"><i class="{cls or meter_class(pct)}" '
            f'style="width:{min(pct, 100):.0f}%"></i></span>'
            f'<span class="pct">{figure}</span></span>')


def pill_bar(pill, meters=(), dual=False, title=None, top=None,
             keep_pill=False):
    """A verdict pill, a figure, and the measurement bar behind both.

    Every column in the table that carries a judgement and the numbers that
    produced it is this one shape: the player-count verdict over its Best and
    Approved percentages, weight over its 1-5 figure, point salad over its
    0-100 score. All three parts ship in the cell and the stylesheet shows the
    ones the reader asked for, so switching the whole table between pills,
    numbers and both costs no re-render and cannot leave two columns
    disagreeing about which line they draw on.

    `top` is the figure as it reads on its own line, where the pill would be —
    which is why a numbers-only table still lines up across a row: the number
    where the pill was, the bar where the bar was.

    Marked `sw`, for switchable: it tells the stylesheet that this cell answers
    to the picker's pills/numbers setting, as against the .pb spans drawn
    elsewhere that do not. `keep_pill` marks the cells whose *pill* is their
    short form, so a compact table prints that instead of the figure: the
    kind of interaction is prose and has no figure at all, and point salad's
    band name says in a word what its score says in a number. The rest print
    the figure, because "3.86" is shorter than "Medium" and says more.

    Mirrored by pillBar() in the page script, which repaints the player-count
    columns whenever the count changes.
    """
    if not pill and not meters and top is None:
        return EM_DASH
    t = f' title="{esc(title)}"' if title else ""
    under = "".join(meters)
    body = pill or ""
    if top is not None:
        body += f'<span class="pbtop">{esc(top)}</span>'
    if under:
        body += '<span class="pbars">' + under + "</span>"
    return (f'<span class="pb sw{" keep-pill" if keep_pill else ""}'
            f'{" dual" if dual else ""}"{t}>{body}</span>')


def salad_pill(band):
    return (f'<span class="tag {SALAD_PILL.get(band, "p1")}">'
            f'{SALAD_SHORT.get(band, band)}</span>') if band else ""


def salad_meter(n):
    # Green is a sharp focus, red is a total salad — the same ramp the weight
    # bar uses, and the bands are the same ones SALAD_BANDS cuts.
    if n is None:
        return ""
    cls = "sl4" if n >= 72 else "sl3" if n >= 40 else "sl2" if n >= 12 else "sl1"
    return meter(n, cls)


def salad_cell(band, n):
    """Point salad: the band, the score and the bar, in one cell.

    `keep_pill`, so a compact table shows "Point salad" rather than 93%: the
    score is a derived number on a scale nobody has memorised, and the band
    name is the part of it a reader can act on.
    """
    title = f"Point salad: {SALAD_LABEL.get(band, band)}" if band else None
    return pill_bar(salad_pill(band),
                    [salad_meter(n)] if n is not None else [],
                    title=title, top=None if n is None else f"{n}%",
                    keep_pill=True)


def pct_text(p):
    return EM_DASH if p is None else f"{p:.0f}%"


def poll_figure(s):
    """The whole vote as one figure, for the line the pill would have taken:
    what share call the count best, and what share merely recommend it."""
    if s["bestPct"] is None:
        return EM_DASH
    rec = max(s["appr"] - s["bestPct"], 0)
    return f'{s["bestPct"]:.0f} / {rec:.0f}%'


def poll_cells(s, n):
    """The three player-count columns: the verdict over the whole vote, over
    the best percentage, and over the approved percentage.

    Each carries the same verdict pill, because the pill is the answer and the
    percentage is the evidence for it; a column showing one without the other
    would make you look at two columns to read one fact. Which half is on
    screen is the picker's pills/numbers setting — the same one weight and
    time answer to, because these are not a special case.
    """
    if not n or not s:
        return EM_DASH, EM_DASH, EM_DASH
    pill = verdict_html(s, n)
    tip = poll_title(s, n)
    both = pill_bar(pill, [poll_stack(s)], title=tip, top=poll_figure(s))
    best = pill_bar(pill, [meter(s["bestPct"])], title=f"Best at {n}p",
                    top=pct_text(s["bestPct"]))
    appr = pill_bar(approved_html(s), [meter(s["appr"])],
                    title=f"Approved at {n}p", top=pct_text(s["appr"]))
    return both, best, appr


def poll_title(s, n):
    if s["bestPct"] is None:
        return f"At {n}p"
    return (f'At {n}p: {s["bestPct"]:.0f}% call it best, '
            f'{max(s["appr"] - s["bestPct"], 0):.0f}% recommended, '
            f'{100 - s["appr"]:.0f}% not — {s["total"]} votes')


def poll_stack(s):
    """One bar carrying the whole vote, the way the expanded row draws it:
    best, then recommended, then the rest. Two separate bars said the same
    thing in twice the height and made the reader add them up."""
    if s["bestPct"] is None:
        return f'<span class="bar"><span class="pct">{EM_DASH}</span></span>'
    rec = max(s["appr"] - s["bestPct"], 0)

    def seg(pct, cls):
        return (f'<i class="{cls}" style="width:{pct:.1f}%"></i>'
                if pct >= 0.5 else "")

    return (f'<span class="bar pollbar">'
            f'<span class="stack">{seg(s["bestPct"], "b")}{seg(rec, "r")}'
            f'{seg(100 - s["appr"], "n")}</span>'
            f'<span class="pct">{s["bestPct"]:.0f}%&nbsp;/&nbsp;{rec:.0f}%</span>'
            f'</span>')


# Half the voters at a count is the line: below it, more people said "not
# recommended" than said the count works at all.
APPROVED_MIN = 50


def approved_html(s):
    """Approved at this count, or not — a yes/no question, so a yes/no pill.

    The Best/Good/Plays verdict belongs to the other two columns: it answers
    "is this the count to play at", which is not what a column headed
    "Approved at 4p" is asking.
    """
    if s["appr"] is None:
        # A CSV-built collection has BGG's recommendation but no percentage.
        return ('<span class="tag p3">Yes</span>' if s.get("good")
                else '<span class="tag p1">No</span>')
    yes = s["appr"] >= APPROVED_MIN
    return (f'<span class="tag {"p3" if yes else "pw"}">'
            f'{"Yes" if yes else "No"}</span>')


# Opinion fields from the local database. A low-confidence entry means the
# model did not recognise the game, so its opinion fields are dropped rather
# than shown — the report never presents a guess as a finding.
def pic_id(url):
    """BGG serves one image under many URLs — the same `picNNNNNNN` behind
    different size and filter transforms — so the URL is useless as an
    identity. The pic id is the thing that is actually the same picture."""
    m = re.search(r"/(pic\d+)\.", url or "")
    return m.group(1) if m else (url or "")


def load_gallery(gid, cover=None):
    """Gallery image URLs cached by scripts/gallery.py, minus the box cover and
    any repeat of another shot. Only URLs travel in the page; the images
    themselves load from BGG when a row is expanded."""
    f = ROOT / "data" / "gallery" / f"{gid}.json"
    if not f.exists():
        return []
    try:
        gal = json.loads(f.read_text())
    except Exception:  # noqa: BLE001
        return []
    seen = {pic_id(cover)} if cover else set()
    out = []
    for im in gal:
        k = pic_id(im.get("u"))
        if k in seen:
            continue
        seen.add(k)
        out.append(im)
    return out[:5]


def trim_ai(ai):
    if not ai:
        return None
    conf = ai.get("confidence", "low")
    facts = ai.get("scoring") or {}
    out = {"cf": conf, "wc": win(facts), "wcs": wins(facts),
           "br": salad(facts), "brn": salad_score(facts),
           "srcs_n": len(facts.get("sources") or []),
           "sc": score_text(facts), "scn": score_sort(facts),
           "scnote": facts.get("score_note") or "",
           "ixl": (ai.get("interaction") or {}).get("level"),
           "ixk": (ai.get("interaction") or {}).get("kind"),
           "ixd": (ai.get("interaction") or {}).get("detail"),
           "howwin": (ai.get("scoring") or {}).get("how_you_win"),
           "teach": ai.get("teachers") or []}
    out["src"] = ai.get("source")
    if conf != "low" or ai.get("source") == "description":
        out["sm"] = ai.get("summary")
        out["up"] = ai.get("praised") or []
        out["dn"] = ai.get("criticised") or []
        out["sim"] = ai.get("similar") or []
        out["srcs"] = (ai.get("sources") or [])[:4]
    return out


def fmt_count(n):
    """60082 -> 60k. The exact figure is on the cell's title."""
    if not n:
        return EM_DASH
    if n >= 10000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def fmt_rating(v, decimals=1):
    """Drop a trailing ".0" — "10" fits the hexagon where "10.0" crowds it, and
    whole numbers are how BGG shows a user's own rating anyway."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.{decimals}f}"


def hexagon(value, title, decimals=1):
    """BGG's rating badge. Used for both the community score and the owner's
    own rating, so the same number means the same colour in both columns. The
    BGG / Mine headers tell the two apart — a ring or border would not, since
    clip-path clips box-shadow away."""
    if not value:
        return '<span class="dot">&mdash;</span>'
    band = max(0, min(10, int(value)))
    return (f'<span class="hex" style="background:{RATING_COLORS[band]}" '
            f'title="{esc(title)}">{fmt_rating(value, decimals)}</span>')


def bgg_hex(g):
    if not g["av"]:
        return '<span class="dot">&mdash;</span>'
    title = f'BGG average {g["av"]:.2f}'
    if g["gk"]:
        title += f' \u00b7 Geek rating {g["gk"]:.2f}'
    # The community average keeps its decimal: 8.1 and 8.6 are different enough
    # to matter when scanning the column.
    band = max(0, min(10, int(g["av"])))
    return (f'<span class="hex" style="background:{RATING_COLORS[band]}" '
            f'title="{esc(title)}">{g["av"]:.1f}</span>')


def mine_hex(g):
    if not g["my"]:
        return '<span class="dot">&mdash;</span>'
    return hexagon(g["my"], f'Your rating {fmt_rating(g["my"])}')


def verdict_html(s, mode_n):
    if not mode_n or not s:
        return '<span class="dot">—</span>'
    # p3/p2/p1 rather than best/good/plays: the same ramp every other pill in
    # the table uses, and the same classes verdictHtml() writes in the page
    # script — the server's pills were unstyled until the script repainted
    # them, which showed as a colour pop on first paint.
    if s["isBest"]:
        return '<span class="tag p3">Best</span>'
    # A CSV-built collection has no percentage, only BGG's recommendation.
    good = s.get("good") if s["bestPct"] is None else s["bestPct"] >= 50
    if good:
        return '<span class="tag p2">Good</span>'
    return '<span class="tag p1">Plays</span>'


def passes_static(g, s, a, mode, via=None):
    """The opening filters, applied server-side so the first paint — and any
    viewer without JavaScript — sees exactly what the controls describe."""
    if g["exp"] and a.expansions != "show":
        return False
    # `via` means an expansion vouched for the count, in which case the base
    # game's own player range is beside the point.
    if a.players and not (via or stands_at(g, s, a.players, mode)):
        return False
    ai = g["ai"] or {}
    # The page's band filters take several values at once; the CLI opens the
    # page on one, so "chosen" is a set of one here and the test is the same
    # on both sides.
    if a.salad != "any" and ai.get("br") not in picks(a.salad):
        return False
    return True


def picks(value):
    """A multi-valued filter as a set. Empty means "no opinion", which every
    game passes — the same reading the page gives an empty pick list."""
    return set(v for v in str(value or "").split(",") if v)


def describe(a):
    """Mirror of describe() in the page script: a short statement of what the
    table is showing, for the first paint and for viewers without JavaScript."""
    head = None
    if a.players:
        head = {"best": f"Games best at {a.players}p",
                "good": f"Games good at {a.players}p"}.get(
                    a.mode, f"Games that play at {a.players}p")

    extra = []
    if a.salad != "any":
        # Several bands read as alternatives, which is what they are.
        extra.append("point salad: " + " or ".join(
            SALAD_LABEL.get(b, b).lower() for b in picks(a.salad)))
    if a.expansions == "drop":
        extra.append("expansions ignored")
    # With a filter applied, "All games, X" is noise — the filter is the subject.
    if head:
        return head + (", " + ", ".join(extra) if extra else "")
    if not extra:
        return ("All games and expansions" if a.expansions == "show"
                else "All games")
    if a.expansions == "show":
        extra.append("including expansions")
    text = ", ".join(extra)
    return text[0].upper() + text[1:]


def fold(text):
    """Accents folded away, so "orleans" finds "Orleans".

    Latin letters that carry a single combining mark come back as one
    character each, so positions survive the fold and the browser-side
    highlighter can still slice the original string by the index it found.
    """
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))


def haystack(g, tags):
    """Everything about a game that the page shows anywhere, as one lowercase
    string to search: the name and year, the designers, every property it
    carries, how it is won, how much of a salad it is, and the interaction
    level. Searching "econo" should find the games tagged Economic, and
    searching a designer or a year should find those too.

    Also BGG's alternate titles, which are never shown: somebody who knows a
    game as Les Chateaux de Bourgogne should still find it.
    """
    ai = g.get("ai") or {}
    bits = [g["n"], str(g["y"] or "")]
    bits += g.get("alt") or []
    bits += g.get("ds") or []
    bits += g.get("pb") or []
    bits += [tags[i]["n"] for i in g.get("tg") or [] if i < len(tags)]
    bits += [WIN_LABEL.get(w, "") for w in ai.get("wcs") or []]
    bits += [SALAD_LABEL.get(ai.get("br"), ""), ai.get("ixl") or g.get("ix") or ""]
    if g.get("exp"):
        bits.append("expansion")
    return fold(" ".join(b for b in bits if b).lower())


def rows_html(data, a, tags=()):
    """Every row, rendered as real markup.

    The page script owns only the cells that change with the player count; the
    rest is static. That keeps one source of truth for the row skeleton and,
    more importantly, means the table is fully readable when the script does
    not run at all — as in Slack's mobile preview.
    """
    by_base = {}
    for g in data:
        if not g["exp"]:
            continue
        for base in g["of"]:
            by_base.setdefault(base, []).append(g)

    n, mode = a.players, a.mode
    fold = a.expansions == "fold"
    out = []
    for i, g in enumerate(data):
        s, via = (reading(g, n, by_base, fold, mode)
                  if n else (None, None))
        shown = passes_static(g, s, a, mode, via)

        thumb = (f'<img class="thumb" loading="lazy" alt="" src="{esc(g["th"])}">'
                 if g["th"] else "")
        badges = ('<span class="tag exp">EXPANSION</span>' if g["exp"] else "")
        # +EXP means "you own expansions for this", and says which on hover.
        # It used to appear only when an expansion was the *reason* the game
        # qualified at the chosen count, which made it vanish from most views
        # of a game that plainly has one — and never showed at all with the
        # count on Any. The narrower fact is still worth saying, so when it
        # holds the badge keeps the same place and says so in the title.
        owned_exp = [e["n"] for e in by_base.get(g["id"], [])]
        if owned_exp:
            tip = (f'Qualifies at {n}p thanks to {via}' if via
                   else "You own: " + ", ".join(owned_exp))
            badges += (f'<span class="tag exp{" via" if via else ""}"'
                       f' data-exp="{esc(", ".join(owned_exp))}"'
                       f' title="{esc(tip)}">+EXP</span>')
        v = verdict_html(s, n)
        w_html = weight_cell(g["w"])
        t_html = time_cell(g)
        ai = g["ai"] or {}
        ix_level = ai.get("ixl") or g["ix"]
        ix_title = ai.get("ixk") or "derived from mechanics"
        ix_pill = (f'<span class="tag {IX_PILL.get(ix_level, "p1")}">'
                   f'{ix_level}</span>')
        kinds = g.get("kinds") or []
        # The level over what kind of interaction it is — the same cell as
        # weight or point salad, with words on the second line instead of a
        # measurement. Up to three kinds, stacked, the type stepping down so
        # they still fit a row: the same treatment win conditions and
        # designers get. A pills-only table shows the level and drops them; a
        # numbers-only one drops the level and shows all three, which is why
        # all three ship in the cell whatever the setting.
        ix_kinds = (
            f'<span class="ixonly n{len(kinds)}"'
            f' title="{esc(", ".join(kinds))}">'
            + "".join(f'<span>{esc(k)}</span>' for k in kinds)
            + '</span>') if kinds else ""
        ix_html = pill_bar(ix_pill, [ix_kinds] if ix_kinds else [],
                           title=ix_title, keep_pill=True)
        ways = ai.get("wcs") or ([ai["wc"]] if ai.get("wc") else [])
        # Every way to win, stacked; the type shrinks so three still fit a row.
        win_html = (
            f'<span class="wc n{len(ways)}" '
            f'title="{esc(" or ".join(WIN_LABEL.get(w, w) for w in ways))}">'
            + "".join(f'<span>{esc(WIN_SHORT.get(w, w))}</span>' for w in ways)
            + '</span>') if ways else EM_DASH
        br = ai.get("br")
        salad_html = salad_cell(br, ai.get("brn"))
        atn_html, best_html, appr_html = poll_cells(s, n)
        who = g["ds"]
        # Up to three designers stacked one per line, the type stepping down
        # so they still fit a row — the same treatment the win conditions get.
        # Past three, the third line carries the +N.
        # `named`, not `shown`: this used to reuse the name that holds whether
        # the row passes the opening filters, twenty lines above and still
        # needed thirty lines below. Every game with a designer therefore
        # rendered as visible however the page was built, so `--players 4`
        # emitted all 265 rows unhidden and said "265 games" until the script
        # ran and corrected it. Only a reader without JavaScript ever saw it.
        if who:
            named = who[:3]
            extra = len(who) - len(named)
            last = (esc(named[-1])
                    + (f' <span class="more">+{extra}</span>' if extra else ''))
            designer = (
                f'<span class="dsl n{len(named)}" title="{esc(", ".join(who))}">'
                + "".join(f'<span>{esc(d)}</span>' for d in named[:-1])
                + f'<span>{last}</span></span>')
        else:
            designer = EM_DASH
        # The designer also rides in the game cell, for the "Game, Year,
        # Designer" column choice and for widths that drop the column.
        who_short = (esc(", ".join(who[:4]))
                     + (f' +{len(who) - 4}' if len(who) > 4 else "")) if who else ""
        # Empty parts are left out entirely: the separator is drawn by CSS
        # between them, so an empty span would leave a stray dot behind.
        meta_html = ((f'<span class="m-yr">{g["y"]}</span>' if g["y"] else "")
                     + (f'<span class="m-ds">{who_short}</span>' if who_short else ""))
        price_html = (f'{g["pp"]:.2f}&nbsp;{esc(g.get("ppc") or "")}'.strip()
                      if g.get("pp") else EM_DASH)
        rank = g["rk"] if g["rk"] else EM_DASH
        inline = f'<span class="vinline">{v}</span>' if n else ""
        # One name column carrying both optional fields, with the picker's
        # "Game column" choice deciding which of them is on screen. This was
        # four columns for a while — Game, Game+Year, Game+Designer,
        # Game+Year+Designer — which put four rows in the column list that
        # were really one row and a setting, and let you tick two of them at
        # once. Whichever field the cell is showing, the standalone column for
        # it stands down: a year in two places at once is a wasted column.
        game_cell = (f'<td class="gamecell c-gn" data-col="gn">'
                     f'<span class="game">{esc(g["n"])}</span>'
                     f'{badges}{inline}'
                     + (f'<span class="meta">{meta_html}</span>'
                        if meta_html else "")
                     + '</td>')
        search = esc(haystack(g, tags))

        out.append(
            f'<tr class="game-row" data-i="{i}" data-search="{search}"{"" if shown else " hidden"}>'
            f'<td class="thumb c-th" data-col="th">{thumb}</td>'
            f'<td class="num hide-sm c-rk" data-col="rk">{rank}</td>'
            f'<td class="num hide-sm c-rt" data-col="rt" title="{g["rt"] or 0} BGG ratings">'
            f'{fmt_count(g["rt"])}</td>'
            f'<td class="score c-av" data-col="av">{bgg_hex(g)}</td>'
            f'<td class="score mine-col c-my" data-col="my">{mine_hex(g)}</td>'
            f'{game_cell}'
            f'<td class="num drop3 c-y" data-col="y">{g["y"] or EM_DASH}</td>'
            f'<td class="drop2 designer c-ds" data-col="ds">{designer}</td>'
            f'<td class="num hide-sm hide-s c-pl" data-col="pl">{g["pl"]}</td>'
            f'<td class="c-tmax" data-col="tmax">{t_html}</td>'
            f'<td class="hide-sm hide-xs c-w" data-col="w">{w_html}</td>'
            f'<td class="hide-sm drop5 c-ixk" data-col="ixk">{ix_html}</td>'
            f'<td class="num hide-sm c-acq" data-col="acq">{g.get("acq") or EM_DASH}</td>'
            f'<td class="num hide-sm c-lp" data-col="lp">{g.get("lp") or EM_DASH}</td>'
            f'<td class="num hide-sm c-ed" data-col="ed">{g.get("ed") or EM_DASH}</td>'
            f'<td class="num hide-sm c-pp" data-col="pp">{price_html}</td>'
            f'<td class="hide-sm drop1 c-win" data-col="win">{win_html}</td>'
            f'<td class="num hide-sm drop1 c-sc" data-col="sc"'
            f'{f" title={esc(ai.get("scnote"))!r}" if ai.get("scnote") else ""}>'
            f'{esc(ai.get("sc") or "") or EM_DASH}</td>'
            f'<td class="hide-sm drop4 c-salad" data-col="salad">'
            f'{salad_html}</td>'
            f'<td class="hide-sm c-atn j-atn" data-col="atn">{atn_html}</td>'
            f'<td class="hide-sm c-bestp j-bestp" data-col="bestp">'
            f'{best_html}</td>'
            f'<td class="hide-sm c-apprp j-apprp" data-col="apprp">'
            f'{appr_html}</td>'
            f'</tr>')
    shown = sum(1 for o in out if not o.startswith(tuple()) and " hidden>" not in o)
    return "\n".join(out), shown


VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source", "col"}


def check_balanced(html):
    """Fail the build on unbalanced markup.

    A single stray </div> in the filter panel once closed the page wrapper
    early, which put the result line and the whole table outside it — they
    stretched to the window edges while the header stayed inset. The page still
    rendered, so nothing caught it but the eye. This does.
    """
    from html.parser import HTMLParser

    body = html[html.index('<div class="wrap">'):html.index("</body>")]

    class Checker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.errors = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in VOID_TAGS:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if not self.stack:
                self.errors.append(f"stray </{tag}>")
            elif self.stack[-1] == tag:
                self.stack.pop()
            else:
                self.errors.append(f"</{tag}> while inside <{self.stack[-1]}>")

    c = Checker()
    c.feed(body)
    problems = c.errors + [f"unclosed <{t}>" for t in c.stack]
    if problems:
        raise SystemExit("unbalanced markup: " + "; ".join(problems[:5]))


# Columns that start hidden. This must agree with COLUMNS[].off in the page
# script AND with the head script's own copy, or the table paints in one shape
# and settles into another. Year was in this list and not in the other two,
# and the symptom was exactly that: the column appeared a moment after the
# page did.
#
# Best and Approved start off: "Good at Np" already carries the whole vote,
# and the other two are for reading one half of it closely. The designer is
# off because the Game column carries it — see root_class().
OFF_BY_DEFAULT = ("acq", "lp", "ed", "sc", "pp", "bestp", "apprp")


# Columns that draw a pill with a second line under it. While any of them is
# on screen the rows need more air, because every one of those cells is twice
# the height of a plain one and the table closes up around them.
#
# The page script and the head script each have their own copy; all three have
# to agree or the row height changes a moment after the page appears.
# They only draw two lines while the pills/numbers setting asks for both,
# which is why root_class() checks that first.
STACKED_COLS = ("tmax", "w", "ixk", "salad", "atn", "bestp", "apprp")
# ...of which these only exist while a player count is chosen.
POLL_COLS = ("atn", "bestp", "apprp")


def owner():
    """Whose collection this is, for the title. Read softly: the report has to
    build without credentials — from a CSV export, or in CI."""
    name = os.environ.get("BGG_USERNAME")
    if name:
        return name.strip()
    f = ROOT / "credentials.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip().startswith("BGG_USERNAME"):
                return line.split("=", 1)[-1].strip()
    # build.py leaves the name here, which is what CI reads: the credentials
    # file is gitignored, the username is not a secret.
    meta = ROOT / "data" / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text()).get("owner")
        except Exception:  # noqa: BLE001
            pass
    return None


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def headline():
    who = owner()
    return f"{who}'s collection" if who else "Board game collection"


def counts(data):
    games = sum(1 for g in data if not g["exp"])
    exps = sum(1 for g in data if g["exp"])
    text = plural(games, "game")
    if exps:
        text += " and " + plural(exps, "expansion")
    return text


def bgg_link():
    who = owner()
    if not who:
        return ""
    return (f'<a href="https://boardgamegeek.com/collection/user/{esc(who)}"'
            f' target="_blank" rel="noopener">Open on BGG ↗</a>')


def root_class(a):
    """The default column state, written into <html> so the first paint is
    already right — for a browser with scripts blocked, and as the base the
    head script swaps out when this browser has chosen something else."""
    # gm-ds: the Game column carries the designer. det-detailed: every
    # switchable cell shows its pill and its number. Both are the defaults the
    # picker starts from, and the head script swaps in whatever this browser
    # chose.
    cls = ["gm-ds", "det-detailed"] + [f"off-{k}" for k in OFF_BY_DEFAULT]
    if not a.players:
        cls.insert(0, "mode-any")
    # The Game column carries the designer, so its own column stands down.
    cls.append("off-ds")
    if any(k not in OFF_BY_DEFAULT and (a.players or k not in POLL_COLS)
           for k in STACKED_COLS):
        cls.append("stacked")
    return " ".join(cls)


def load_private():
    """Price paid and acquisition date, read at render time from a gitignored
    CSV export — never from data/games.json.

    BGG keeps these in the private part of a collection entry and the XML API
    never returns them, so they can only come from the CSV you download
    yourself. They are also nobody else's business: keeping them out of the
    normalised data means the committed file and any report built without the
    CSV (CI's, for instance) cannot carry them by accident.
    """
    f = ROOT / "data" / "collection.csv"
    if not f.exists():
        return {}
    import csv
    out = {}
    with f.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            oid = row.get("objectid")
            if not oid or row.get("own") != "1":
                continue
            rec = {}
            price = (row.get("pricepaid") or "").strip()
            if price and price not in ("0.00", "0"):
                try:
                    rec["pp"] = float(price)
                except ValueError:
                    pass
                rec["ppc"] = (row.get("pp_currency") or "").strip()
            acq = (row.get("acquisitiondate") or "").strip()
            if acq:
                rec["acq"] = acq[:10]
            if rec:
                out[oid] = rec
    return out


def repo_url():
    """The GitHub link in the corner, read from the checkout's own origin so a
    fork points at itself. Falls back to this project's home."""
    default = "https://github.com/peterlevi/my-boardgames"
    try:
        out = subprocess.run(["git", "-C", str(HERE.parent), "config",
                              "--get", "remote.origin.url"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return default
    if not out:
        return default
    if out.startswith("git@"):                      # git@github.com:user/repo.git
        out = "https://" + out[4:].replace(":", "/", 1)
    return out[:-4] if out.endswith(".git") else out


def warn_if_stale():
    """Say so when the opinion database has moved on and games.json has not.

    The page renders from the `ai` payload that build.py copies into
    games.json, never from data/ai/ directly, so an enrich.py run that is not
    followed by a build.py run changes nothing on screen. That silence is the
    trap: the scoring checks read data/ai/ and report a new number while the
    report still shows the old labels, and the two disagree with no error
    anywhere. A mtime comparison is enough to catch it.
    """
    games = ROOT / "data" / "games.json"
    ai = ROOT / "data" / "ai"
    if not games.exists() or not ai.is_dir():
        return
    newer = [f.name for f in ai.glob("*.json")
             if f.stat().st_mtime > games.stat().st_mtime]
    if newer:
        print(f"warning: {len(newer)} opinion record(s) are newer than "
              f"data/games.json ({', '.join(sorted(newer)[:3])}"
              f"{'...' if len(newer) > 3 else ''}). "
              f"Run `python3 scripts/build.py` first or the page will show "
              f"stale labels.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=0,
                    help="player count the page opens on (0 = any)")
    ap.add_argument("--mode", choices=["best", "good", "any"], default="good",
                    help="opening player-count rule")
    # The band keys, not the words they print. These read "Focused, Some,
    # Broad, Salad" until now — a vocabulary from before the bands were
    # renamed — so every use of the flag either raised a KeyError in
    # describe() or, past that, matched no game at all. Comma-separated,
    # because the page's own point-salad filter takes several bands and the
    # flag chooses the state the page opens in.
    ap.add_argument("--salad", default="any",
                    help="opening point-salad bands, comma-separated: "
                         + ", ".join(SALAD_LABEL) + ", or any")
    ap.add_argument("--expansions", choices=["fold", "show", "drop"],
                    default="fold", help="fold: hide expansion rows but let "
                                         "them speak for their base game")
    ap.add_argument("--link-thumbs", action="store_true",
                    help="hotlink thumbnails to BGG instead of inlining them")
    ap.add_argument("-o", "--out", default="reports/collection.html")
    a = ap.parse_args()
    bad = [b for b in picks(a.salad) if b not in SALAD_LABEL]
    if a.salad != "any" and bad:
        raise SystemExit(f"unknown point salad band(s): {', '.join(bad)}. "
                         f"Choose from {', '.join(SALAD_LABEL)}, or any.")

    warn_if_stale()
    games = load_games()
    # Before the index, so the derived vocabularies are indexed with the rest.
    annotate(games)
    tags, tag_idx = tag_index(games)
    data = compact(games, tag_idx, inline=not a.link_thumbs,
                   private=load_private())
    # The page opens sorted by rank; emit the rows that way so a viewer with no
    # JavaScript gets the same order rather than raw cache order.
    data.sort(key=lambda g: (g["rk"] is None, g["rk"] or 10 ** 9))
    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    # The multi-valued filters open empty — "no opinion" — rather than on the
    # word "any", so the page's own reading of an empty pick list is the only
    # one there is. The CLI still opens the page on a single band.
    opts = {"players": a.players, "mode": a.mode,
            "salad": "" if a.salad == "any" else a.salad,
            "ix": "", "wband": "", "tband": "",
            "expansions": a.expansions}

    rows, shown = rows_html(data, a, tags)
    def options(pairs, current):
        return "".join(
            f'<option value="{esc(v)}"{" selected" if v == current else ""}>'
            f'{label}</option>' for v, label in pairs)

    players = options([(str(i), "Any" if i == 0 else
                        f"{i} player" + ("" if i == 1 else "s"))
                       for i in range(0, 9)], str(a.players))
    # Named for the count the page opens on. render() rewrites these whenever
    # the count changes; this is the first paint, and what a reader with no
    # JavaScript sees.
    at = f"{a.players}p" if a.players else "N"
    modes = options([("any", f"Plays at {at}"),
                     ("good", f"Good at {at}"),
                     ("best", f"Best at {at}")], a.mode)
    # Short enough that nine filters fit one row. "Hide, but count for base
    # game" was the clearest phrasing and also the widest control in the
    # panel; "factor in" says the same thing in a third of the width, and the
    # full sentence is a hover away.
    exps = options([("fold", "Hide, but factor in"),
                    ("show", "Show as own rows"),
                    ("drop", "Ignore completely")], a.expansions)

    # Drop the thumbnail from the JSON payload once the rows are rendered:
    # the markup already carries each data URI, and shipping it twice doubled
    # the file size.
    for g in data:
        g.pop("th", None)

    html = (tpl
            .replace("<!--__ROWS__-->", rows)
            .replace("<!--__OPTIONS__-->", players)
            .replace("<!--__MODE_OPTIONS__-->", modes)
            .replace("<!--__EXP_OPTIONS__-->", exps)
            # The band tables travel as data rather than being written out a
            # second time in JavaScript: the filter, the pill and the column
            # all read the same rows, so they cannot drift apart.
            .replace("/*__BANDS__*/", json.dumps(
                {"weight": WEIGHT_BANDS, "time": TIME_BANDS,
                 "timeFull": TIME_FULL,
                 # The interaction kinds the classifier can produce, in the
                 # order it tries them, so the filter offers exactly what the
                 # column can show.
                 "ixkinds": ix_kinds(),
                 "scales": scales()}))
            .replace("__SHOWN__", str(shown))
            .replace("__DESC__", esc(describe(a)))
            .replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False,
                                                separators=(",", ":")))
            .replace("/*__OPTS__*/", json.dumps(opts))
            .replace("/*__TAGS__*/", json.dumps(tags, ensure_ascii=False,
                                                separators=(",", ":")))
            # The poll columns are named after the count they read. render()
            # rewrites these when the count changes; this is the first paint.
            .replace("__ATN__", f"Good at {a.players}p" if a.players else "Good at N")
            .replace("__BESTATN__",
                     f"Best at {a.players}p" if a.players else "Best at N")
            .replace("__APPRATN__",
                     f"Appr at {a.players}p" if a.players else "Appr at N")
            .replace("__ROOTCLASS__", root_class(a))
            .replace("__REPO_URL__", esc(repo_url()))
            .replace("__STAMP__", dt.date.today().isoformat())
            .replace("__HEADLINE__", esc(headline()))
            .replace("__COUNTS__", esc(counts(data)))
            .replace("<!--__BGGLINK__-->", bgg_link())
            .replace("__NGAMES__", str(sum(1 for g in data if not g["exp"])))
            .replace("__NEXP__", str(sum(1 for g in data if g["exp"]))))

    check_balanced(html)

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{len(data)} rows -> {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()