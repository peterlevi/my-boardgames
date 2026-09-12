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
import re
import subprocess
from pathlib import Path

from common import ROOT, load_games, playtime, load_overrides

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
    tags = [{"n": name, "k": label[kind], "c": counts[(kind, name)],
             "d": desc.get(name, "")} for kind, name in keys]
    return tags, idx


def compact(games, tag_idx, inline=True):
    """Trim to what the page actually renders, and precompute per-game values
    the browser would otherwise recompute on every keystroke."""
    out, missing = [], 0
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
            "th": thumb, "w": g["weight"], "av": g["average"],
            "gk": g["geek"], "my": g["my_rating"],
            "tmin": g["minplaytime"], "tmax": g["maxplaytime"],
            "pmin": g["minplayers"], "pmax": g["maxplayers"],
            "pl": g["plays"], "ds": g["designers"],
            "dsid": g.get("designer_ids") or {},
            "lp": g.get("last_played"), "acq": g.get("acquired"),
            "pp": g.get("price_paid"), "ppc": g.get("currency"),
            "ed": g.get("edited"),
            "rt": g["ratings"], "ow": g["owners"],
            "de": (g["description"] or "")[:900],
            "mn": g["minplayers"], "mx": g["maxplayers"],
            "ai": trim_ai(g.get("ai")),
            "img": g.get("image"), "vid": g.get("videos") or [],
            "gal": load_gallery(g["id"], g.get("image")),
            "ix": g["interaction"], "exp": 1 if g["is_expansion"] else 0,
            "of": g["expands"] or [], "t": playtime(g),
            "top": max((v[0] for v in poll.values()), default=0),
            "bestAt": g.get("best_at") or [],
            "recAt": g.get("rec_at") or [],
            "poll": poll,
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
BREADTH_PILL = {"Focused": "p3", "Some": "p2", "Broad": "p1", "Salad": "pw"}
# The stored values stay Focused/Some/Broad/Salad — that is what the opinion
# database writes — but nobody says "breadth" about a board game, so the
# column, the filter and its options all talk about point salad instead.
BREADTH_LABELS = {
    "Focused": "No, sharp focus",
    "Some": "Just a touch",
    "Broad": "Quite a lot",
    "Salad": "Total point salad",
}
# Room in the column is tighter than in the dropdown.
BREADTH_SHORT = {
    "Focused": "No", "Some": "A touch",
    "Broad": "Quite a lot", "Salad": "Total salad",
}
# Column headings must be short; the full phrase stays in the filter.
WIN_SHORT = {
    "Most points, many sources": "Points, many sources",
    "Most points, one or two sources": "Points, few sources",
    "Most money": "Money", "Race to a finish": "Race",
    "Lowest-highest scoring": "Low-high",
    "Special win condition": "Special", "Cooperative goal": "Co-op goal",
    "Other": "Other",
}
WIN_CRITERIA = list(WIN_SHORT)



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
    if not fold or g["exp"] or qualifies(s, mode):
        return s, None
    for e in by_base.get(g["id"], []):
        cand = stats_at(e, n)
        if not cand:
            continue
        if qualifies(cand, mode):
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


def weight_bar(w):
    """Weight reads faster as a colour than as a number: green for light,
    red for heavy, the fill showing where it sits on BGG's 1-5 scale."""
    if not w:
        return EM_DASH
    cls = "wt4" if w >= 4 else "wt3" if w >= 3 else "wt2" if w >= 2 else "wt1"
    return (f'<span class="pct">{w:.2f}</span><span class="track">'
            f'<i class="{cls}" style="width:{min(w / 5 * 100, 100):.0f}%"></i>'
            f'</span>')


def bar(pct):
    if pct is None:
        return EM_DASH
    return (f'<span class="pct">{pct:.0f}%</span><span class="track">'
            f'<i class="{meter_class(pct)}" '
            f'style="width:{min(pct, 100):.0f}%"></i></span>')


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
    out = {"cf": conf, "wc": ai.get("win_criteria"),
           "br": (ai.get("scoring") or {}).get("breadth"),
           "why": (ai.get("scoring") or {}).get("why"),
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
    if s["isBest"]:
        return '<span class="tag best">Best</span>'
    # A CSV-built collection has no percentage, only BGG's recommendation.
    good = s.get("good") if s["bestPct"] is None else s["bestPct"] >= 50
    if good:
        return '<span class="tag good">Good</span>'
    return '<span class="dot">plays</span>'


def passes_static(g, s, a, mode):
    """The opening filters, applied server-side so the first paint — and any
    viewer without JavaScript — sees exactly what the controls describe."""
    if g["exp"] and a.expansions != "show":
        return False
    if a.players and not qualifies(s, mode):
        return False
    ai = g["ai"] or {}
    if a.win != "any" and ai.get("wc") != a.win:
        return False
    if a.breadth != "any" and ai.get("br") != a.breadth:
        return False
    return True


def describe(a):
    """Mirror of describe() in the page script: a short statement of what the
    table is showing, for the first paint and for viewers without JavaScript."""
    head = None
    if a.players:
        head = {"best": f"Games best at {a.players}p",
                "good": f"Games good at {a.players}p"}.get(
                    a.mode, f"Games that play at {a.players}p")

    extra = []
    if a.win != "any":
        extra.append(WIN_SHORT.get(a.win, a.win).lower())
    if a.breadth != "any":
        extra.append(a.breadth.lower() + " scoring")
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


def rows_html(data, a):
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
        shown = passes_static(g, s, a, mode)

        thumb = (f'<img class="thumb" loading="lazy" alt="" src="{esc(g["th"])}">'
                 if g["th"] else "")
        badges = ('<span class="tag exp">EXPANSION</span>' if g["exp"] else "")
        if via:
            badges += f'<span class="tag exp" title="{esc(via)}">+EXP</span>'
        v = verdict_html(s, n)
        weight = weight_bar(g["w"])
        ai = g["ai"] or {}
        ix_level = ai.get("ixl") or g["ix"]
        ix_html = (f'<span class="tag {IX_PILL.get(ix_level, "p1")}"'
                   f' title="{esc(ai.get("ixk") or "derived from mechanics")}">'
                   f'{ix_level}</span>')
        win_html = (f'<span class="wc" title="{esc(ai.get("why") or "")}">'
                    f'{esc(WIN_SHORT.get(ai.get("wc"), ai.get("wc") or EM_DASH))}'
                    f'</span>')
        br = ai.get("br")
        br_html = (f'<span class="tag {BREADTH_PILL.get(br, "p1")}"'
                   f' title="Point salad: {esc(BREADTH_LABELS.get(br, br))}">'
                   f'{BREADTH_SHORT.get(br, br)}</span>' if br else EM_DASH)
        who = g["ds"]
        designer = (f'<span title="{esc(", ".join(who))}">{esc(who[0])}'
                    + (f' <span class="more">+{len(who) - 1}</span>'
                       if len(who) > 1 else '') + '</span>') if who else EM_DASH
        # The designer also rides in the game cell, for the "Game, Year,
        # Designer" column choice and for widths that drop the column.
        who_short = (esc(", ".join(who[:2]))
                     + (f' +{len(who) - 2}' if len(who) > 2 else "")) if who else ""
        # Empty parts are left out entirely: the separator is drawn by CSS
        # between them, so an empty span would leave a stray dot behind.
        meta_html = ((f'<span class="m-yr">{g["y"]}</span>' if g["y"] else "")
                     + (f'<span class="m-ds">{who_short}</span>' if who_short else ""))
        price_html = (f'{g["pp"]:.2f}&nbsp;{esc(g.get("ppc") or "")}'.strip()
                      if g.get("pp") else EM_DASH)
        rank = g["rk"] if g["rk"] else EM_DASH
        inline = f'<span class="vinline">{v}</span>' if n else ""
        search = esc(f'{g["n"]} {g["y"] or ""}'.lower())

        out.append(
            f'<tr class="game-row" data-i="{i}" data-search="{search}"{"" if shown else " hidden"}>'
            f'<td class="thumb c-th" data-col="th">{thumb}</td>'
            f'<td class="num hide-sm c-rk" data-col="rk">{rank}</td>'
            f'<td class="score c-av" data-col="av">{bgg_hex(g)}</td>'
            f'<td class="score mine-col c-my" data-col="my">{mine_hex(g)}</td>'
            f'<td class="gamecell c-n" data-col="n">'
            f'<span class="game">{esc(g["n"])}</span> '
            f'<span class="yr">{g["y"] or ""}</span>{badges}{inline}'
            f'<span class="meta">{meta_html}</span></td>'
            f'<td class="num c-y" data-col="y">{g["y"] or EM_DASH}</td>'
            f'<td class="hide-md designer c-ds" data-col="ds">{designer}</td>'
            f'<td class="num hide-sm hide-s c-pl" data-col="pl">{g["pl"]}</td>'
            f'<td class="num c-tmax" data-col="tmax">{esc(g["t"])}</td>'
            f'<td class="num bar hide-sm hide-xs c-w" data-col="w">{weight}</td>'
            f'<td class="hide-sm hide-xs c-ix" data-col="ix">{ix_html}</td>'
            f'<td class="num hide-sm c-acq" data-col="acq">{g.get("acq") or EM_DASH}</td>'
            f'<td class="num hide-sm c-lp" data-col="lp">{g.get("lp") or EM_DASH}</td>'
            f'<td class="num hide-sm c-ed" data-col="ed">{g.get("ed") or EM_DASH}</td>'
            f'<td class="num hide-sm c-pp" data-col="pp">{price_html}</td>'
            f'<td class="hide-sm hide-lg c-win" data-col="win">{win_html}</td>'
            f'<td class="hide-sm hide-lg c-breadth" data-col="breadth">{br_html}</td>'
            f'<td class="num hide-sm c-verdict j-verdict" data-col="verdict">{v}</td>'
            f'<td class="num bar hide-sm wide-only c-bestPct j-best" data-col="bestPct">'
            f'{bar(s["bestPct"]) if s else EM_DASH}</td>'
            f'<td class="num bar hide-sm c-appr j-appr" data-col="appr">'
            f'{bar(s["appr"]) if s else EM_DASH}</td>'
            f'<td class="num hide-sm c-rt" data-col="rt" title="{g["rt"] or 0} BGG ratings">'
            f'{fmt_count(g["rt"])}</td>'
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=0,
                    help="player count the page opens on (0 = any)")
    ap.add_argument("--mode", choices=["best", "good", "any"], default="good",
                    help="opening player-count rule")
    ap.add_argument("--win", default="any")
    ap.add_argument("--breadth", default="any",
                    choices=["any", "Focused", "Some", "Broad", "Salad"])
    ap.add_argument("--expansions", choices=["fold", "show", "drop"],
                    default="fold", help="fold: hide expansion rows but let "
                                         "them speak for their base game")
    ap.add_argument("--link-thumbs", action="store_true",
                    help="hotlink thumbnails to BGG instead of inlining them")
    ap.add_argument("-o", "--out", default="reports/collection.html")
    a = ap.parse_args()

    games = load_games()
    tags, tag_idx = tag_index(games)
    data = compact(games, tag_idx, inline=not a.link_thumbs)
    # The page opens sorted by rank; emit the rows that way so a viewer with no
    # JavaScript gets the same order rather than raw cache order.
    data.sort(key=lambda g: (g["rk"] is None, g["rk"] or 10 ** 9))
    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    opts = {"players": a.players, "mode": a.mode, "win": a.win,
            "breadth": a.breadth,
            "expansions": a.expansions}

    rows, shown = rows_html(data, a)
    def options(pairs, current):
        return "".join(
            f'<option value="{esc(v)}"{" selected" if v == current else ""}>'
            f'{label}</option>' for v, label in pairs)

    players = options([(str(i), "Any" if i == 0 else f"{i} players")
                       for i in range(0, 9)], str(a.players))
    modes = options([("any", "Plays at that count"),
                     ("good", "Good at that count"),
                     ("best", "Best at that count")], a.mode)
    wins = options([("any", "Doesn't matter")]
                   + [(w, w) for w in WIN_CRITERIA], a.win)
    breadths = options([("any", "Doesn't matter")]
                       + [(b, l) for b, l in BREADTH_LABELS.items()],
                       a.breadth)
    exps = options([("fold", "Hide, but count for base game"),
                    ("show", "Show as their own rows"),
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
            .replace("<!--__WIN_OPTIONS__-->", wins)
            .replace("<!--__BREADTH_OPTIONS__-->", breadths)
            .replace("__SHOWN__", str(shown))
            .replace("__DESC__", esc(describe(a)))
            .replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False,
                                                separators=(",", ":")))
            .replace("/*__OPTS__*/", json.dumps(opts))
            .replace("/*__TAGS__*/", json.dumps(tags, ensure_ascii=False,
                                                separators=(",", ":")))
            .replace("__ATN__", f"At {a.players}p" if a.players else "At N")
            .replace("__TABLECLASS__",
                     ("gm-ds" if a.players else "mode-any gm-ds"))
            .replace("__REPO_URL__", esc(repo_url()))
            .replace("__STAMP__", dt.date.today().isoformat())
            .replace("__NGAMES__", str(sum(1 for g in data if not g["exp"])))
            .replace("__NEXP__", str(sum(1 for g in data if g["exp"]))))

    check_balanced(html)

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{len(data)} rows -> {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()