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

from common import add_filter_args, playtime, select


def main():
    ap = add_filter_args(argparse.ArgumentParser())
    ap.add_argument("--format", choices=["txt", "md", "json"], default="txt")
    a = ap.parse_args()
    rows = select(a)

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
        t = playtime(g)
        verdict = "—" if not s else ("Best" if s["is_best"] else "Great")
        cells = [str(g["rank"] or "—"), g["name"], t,
                 f'{g["weight"]:.2f}' if g["weight"] else "—", verdict,
                 f'{s["best_pct"]:.0f}%' if s else "—",
                 f'{s["approval"]:.0f}%' if s else "—",
                 str(s["total"]) if s else "—"]
        if a.format == "md":
            print("| " + " | ".join(cells) + " |")
        else:
            print(f"{cells[0]:>6}  {g['name'][:44]:<44} {t:>9}  "
                  f"w{cells[3]:<5} {verdict:<5} best {cells[5]:>4} "
                  f"appr {cells[6]:>4} ({cells[7]}v)")
    print(f"\n{len(rows)} games")


if __name__ == "__main__":
    main()
