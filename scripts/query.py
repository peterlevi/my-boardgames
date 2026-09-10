#!/usr/bin/env python3
"""Filter the collection by player count and print a table.

    python3 scripts/query.py --players 4
    python3 scripts/query.py --players 3 --min-best 60 --max-weight 3.0
    python3 scripts/query.py --players 4 --exclude-file point-salads.txt --format md

"Best at N"  = N has more Best votes than any other player count.
"Great at N" = at least --min-best percent of voters called N the Best count.
Approval at N = (Best + Recommended) / all votes for N.
"""
import argparse
import json

from common import ROOT


def poll_stats(g, n):
    d = g["poll"].get(str(n))
    if not d:
        return None
    best, rec, nr = (d.get("Best", 0), d.get("Recommended", 0),
                     d.get("Not Recommended", 0))
    total = best + rec + nr
    if total == 0:
        return None
    top = max((v.get("Best", 0) for v in g["poll"].values()), default=0)
    return dict(best=best, total=total, best_pct=100 * best / total,
                approval=100 * (best + rec) / total,
                is_best=(best == top and best > 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--min-votes", type=int, default=10,
                    help="ignore games with fewer poll votes at this count")
    ap.add_argument("--min-best", type=float, default=50.0,
                    help="'great at N' threshold, in percent")
    ap.add_argument("--min-approval", type=float, default=0.0)
    ap.add_argument("--max-weight", type=float)
    ap.add_argument("--min-weight", type=float)
    ap.add_argument("--max-time", type=int, help="max of maxplaytime, minutes")
    ap.add_argument("--exclude-file",
                    help="file of game names to drop, one per line, # = comment")
    ap.add_argument("--format", choices=["txt", "md", "json"], default="txt")
    a = ap.parse_args()

    games = json.loads((ROOT / "data" / "games.json").read_text())

    excluded = set()
    if a.exclude_file:
        for line in (ROOT / a.exclude_file).read_text().splitlines():
            line = line.split("#")[0].strip()
            if line:
                excluded.add(line)

    rows = []
    for g in games:
        s = poll_stats(g, a.players)
        if not s or s["total"] < a.min_votes:
            continue
        if not (s["is_best"] or s["best_pct"] >= a.min_best):
            continue
        if s["approval"] < a.min_approval:
            continue
        if g["name"] in excluded:
            continue
        w = g["weight"]
        if a.max_weight and (w is None or w > a.max_weight):
            continue
        if a.min_weight and (w is None or w < a.min_weight):
            continue
        if a.max_time and (g["maxplaytime"] or 0) > a.max_time:
            continue
        rows.append((g, s))

    rows.sort(key=lambda r: (r[0]["rank"] is None, r[0]["rank"] or 10**9))

    if a.format == "json":
        print(json.dumps([{**g, "stats": s} for g, s in rows], indent=1,
                         ensure_ascii=False))
        return

    n = a.players
    hdr = ["BGG rank", "Game", "Time (min)", "Weight", f"{n}p verdict",
           f"Best@{n}", f"Approval@{n}", "Votes"]
    if a.format == "md":
        print("| " + " | ".join(hdr) + " |")
        print("|---:|---|---|---:|---|---:|---:|---:|")
    for g, s in rows:
        lo, hi = g["minplaytime"], g["maxplaytime"]
        t = str(lo) if lo == hi else f"{lo}–{hi}"
        verdict = "Best" if s["is_best"] else "Great"
        cells = [str(g["rank"] or "—"), g["name"], t,
                 f'{g["weight"]:.2f}' if g["weight"] else "—", verdict,
                 f'{s["best_pct"]:.0f}%', f'{s["approval"]:.0f}%',
                 str(s["total"])]
        if a.format == "md":
            print("| " + " | ".join(cells) + " |")
        else:
            print(f"{cells[0]:>6}  {g['name'][:44]:<44} {t:>9}  "
                  f"w{cells[3]:<5} {verdict:<5} best {cells[5]:>4} "
                  f"appr {cells[6]:>4} ({cells[7]}v)")
    print(f"\n{len(rows)} games")


if __name__ == "__main__":
    main()
