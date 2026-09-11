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
from pathlib import Path

from common import ROOT, load_games, playtime

THUMBS = ROOT / "data" / "thumbs"

HERE = Path(__file__).resolve().parent


def thumb_uri(game):
    """A base64 data URI for the cached, downscaled thumbnail, or None."""
    f = THUMBS / f'{game["id"]}.jpg'
    if not f.exists():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


def compact(games, inline=True):
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
            "gk": g["geek"],
            "tmin": g["minplaytime"], "tmax": g["maxplaytime"],
            "pmin": g["minplayers"], "pmax": g["maxplayers"],
            "pl": g["plays"], "sal": 1 if g["point_salad"] else 0,
            "ix": g["interaction"], "exp": 1 if g["is_expansion"] else 0,
            "of": g["expands"], "t": playtime(g),
            "top": max((v[0] for v in poll.values()), default=0),
            "poll": poll,
        })
    if missing:
        print(f"warning: {missing} thumbnails not cached, hotlinked instead — "
              f"run scripts/thumbs.py")
    return out


RATING_COLORS = ["#a03530", "#a03530", "#b3414c", "#b94a75", "#a9518f",
                 "#8560a4", "#5b71ac", "#3778a8", "#3f8a5f", "#2d7a4d",
                 "#1d6b40"]


def esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def stats_at(g, n):
    """Mirror of statsAt() in the page script."""
    d = g["poll"].get(str(n))
    if not d:
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
        return s["isBest"] or s["bestPct"] >= 50
    return True


def reading(g, n, by_base, fold, min_votes, mode):
    s = stats_at(g, n)
    if s and s["total"] < min_votes:
        s = None
    if not fold or g["exp"] or qualifies(s, mode):
        return s, None
    for e in by_base.get(g["id"], []):
        cand = stats_at(e, n)
        if not cand or cand["total"] < min_votes:
            continue
        if qualifies(cand, mode):
            return cand, e["n"]
    return s, None


def bar(pct):
    return (f'{pct:.0f}%<span><i style="width:{min(pct, 100):.0f}%"></i></span>')


def hexagon(g):
    if not g["av"]:
        return '<span class="hex none">—</span>'
    band = max(0, min(10, int(g["av"])))
    title = f'Average {g["av"]:.2f}'
    if g["gk"]:
        title += f' · Geek rating {g["gk"]:.2f}'
    return (f'<span class="hex" style="background:{RATING_COLORS[band]}" '
            f'title="{esc(title)}">{g["av"]:.1f}</span>')


def verdict_html(s, mode_n):
    if not mode_n or not s:
        return '<span class="dot">—</span>'
    if s["isBest"]:
        return '<span class="tag best">Best</span>'
    if s["bestPct"] >= 50:
        return '<span class="tag good">Good</span>'
    return '<span class="dot">plays</span>'


def passes_static(g, s, a, mode):
    """The opening filters, applied server-side so the first paint — and any
    viewer without JavaScript — sees exactly what the controls describe."""
    if g["exp"] and a.expansions != "show":
        return False
    if a.salad == "no" and g["sal"]:
        return False
    if a.salad == "yes" and not g["sal"]:
        return False
    if a.players and not qualifies(s, mode):
        return False
    return True


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
        s, via = (reading(g, n, by_base, fold, a.min_votes, mode)
                  if n else (None, None))
        shown = passes_static(g, s, a, mode)

        thumb = (f'<img class="thumb" loading="lazy" alt="" src="{esc(g["th"])}">'
                 if g["th"] else "")
        badges = ('<span class="tag exp">EXPANSION</span>' if g["exp"] else "")
        if via:
            badges += f'<span class="tag exp" title="{esc(via)}">+EXP</span>'
        v = verdict_html(s, n)
        inline = f'<span class="vinline">{v}</span>' if n else ""
        search = esc(f'{g["n"]} {g["y"] or ""}'.lower())

        out.append(
            f'<tr data-i="{i}" data-search="{search}"{"" if shown else " hidden"}>'
            f'<td class="thumb">{thumb}</td>'
            f'<td class="num hide-sm">{g["rk"] if g["rk"] else chr(8212)}</td>'
            f'<td class="score">{hexagon(g)}</td>'
            f'<td><a class="game" href="https://boardgamegeek.com/boardgame/{g["id"]}"'
            f' target="_blank" rel="noopener">{esc(g["n"])}</a> '
            f'<span class="yr">{g["y"] or ""}</span>{badges}{inline}</td>'
            f'<td class="num hide-sm">{g["pl"]}</td>'
            f'<td class="num">{esc(g["t"])}</td>'
            f'<td class="num">{f"{g["w"]:.2f}" if g["w"] else chr(8212)}</td>'
            f'<td class="hide-sm"><span class="ix {g["ix"]}">{g["ix"]}</span></td>'
            f'<td class="num hide-sm">{"yes" if g["sal"] else "no"}</td>'
            f'<td class="num hide-sm j-verdict">{v}</td>'
            f'<td class="num bar hide-sm j-best">{bar(s["bestPct"]) if s else chr(8212)}</td>'
            f'<td class="num bar hide-sm j-appr">{bar(s["appr"]) if s else chr(8212)}</td>'
            f'<td class="num hide-sm j-votes">{s["total"] if s else chr(8212)}</td>'
            f'</tr>')
    shown = sum(1 for o in out if not o.startswith(tuple()) and " hidden>" not in o)
    return "\n".join(out), shown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=4,
                    help="player count the page opens on (0 = any)")
    ap.add_argument("--mode", choices=["best", "good", "any"], default="good",
                    help="opening player-count rule")
    ap.add_argument("--salad", choices=["any", "no", "yes"], default="no")
    ap.add_argument("--expansions", choices=["fold", "show", "drop"],
                    default="fold", help="fold: hide expansion rows but let "
                                         "them speak for their base game")
    ap.add_argument("--min-votes", type=int, default=10)
    ap.add_argument("--link-thumbs", action="store_true",
                    help="hotlink thumbnails to BGG instead of inlining them")
    ap.add_argument("-o", "--out", default="reports/collection.html")
    a = ap.parse_args()

    games = load_games()
    data = compact(games, inline=not a.link_thumbs)
    # The page opens sorted by rank; emit the rows that way so a viewer with no
    # JavaScript gets the same order rather than raw cache order.
    data.sort(key=lambda g: (g["rk"] is None, g["rk"] or 10 ** 9))
    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    opts = {"players": a.players, "mode": a.mode, "salad": a.salad,
            "expansions": a.expansions, "minVotes": a.min_votes}

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
    salads = options([("any", "Doesn't matter"), ("no", "No — exclude salads"),
                      ("yes", "Yes — only salads")], a.salad)
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
            .replace("<!--__SALAD_OPTIONS__-->", salads)
            .replace("<!--__EXP_OPTIONS__-->", exps)
            .replace("__MINVOTES__", str(a.min_votes))
            .replace("__SHOWN__", str(shown))
            .replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False,
                                                separators=(",", ":")))
            .replace("/*__OPTS__*/", json.dumps(opts))
            .replace("__STAMP__", dt.date.today().isoformat())
            .replace("__NGAMES__", str(sum(1 for g in data if not g["exp"])))
            .replace("__NEXP__", str(sum(1 for g in data if g["exp"]))))

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{len(data)} rows -> {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
