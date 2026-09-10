#!/usr/bin/env python3
"""Render the whole collection as a standalone, filterable HTML report.

    python3 scripts/report.py -o reports/collection.html
    python3 scripts/report.py --players 4 --mode best -o reports/best-at-4.html

Unlike query.py this does not filter server-side: every owned game is embedded
in the page and all filtering happens in the browser, so one file answers any
question. The CLI flags only choose which filters the page *opens* with.

Thumbnails are hotlinked to BGG's image CDN and lazy-loaded, so the file stays
small and generating it costs zero API calls — but it needs internet to show
the pictures.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

from common import ROOT, load_games, playtime

HERE = Path(__file__).resolve().parent


def compact(games):
    """Trim to what the page actually renders, and precompute per-game values
    the browser would otherwise recompute on every keystroke."""
    out = []
    for g in games:
        poll = {}
        for n, d in g["poll"].items():
            b, r, x = (d.get("Best", 0), d.get("Recommended", 0),
                       d.get("Not Recommended", 0))
            if b + r + x:
                poll[n] = [b, r, x]
        out.append({
            "id": g["id"], "n": g["name"], "y": g["year"], "rk": g["rank"],
            "th": g["thumbnail"], "w": g["weight"], "av": g["average"],
            "tmin": g["minplaytime"], "tmax": g["maxplaytime"],
            "pmin": g["minplayers"], "pmax": g["maxplayers"],
            "pl": g["plays"], "sal": 1 if g["point_salad"] else 0,
            "ix": g["interaction"], "exp": 1 if g["is_expansion"] else 0,
            "of": g["expands"], "t": playtime(g),
            "top": max((v[0] for v in poll.values()), default=0),
            "poll": poll,
        })
    return out


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
    ap.add_argument("-o", "--out", default="reports/collection.html")
    a = ap.parse_args()

    games = load_games()
    data = compact(games)
    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    opts = {"players": a.players, "mode": a.mode, "salad": a.salad,
            "expansions": a.expansions, "minVotes": a.min_votes}

    html = (tpl
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
