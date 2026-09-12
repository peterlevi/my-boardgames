#!/usr/bin/env python3
"""Score an interaction scheme against the owner's calls in tests/interaction_calls.txt.

Usage:  python3 scripts/check_interaction.py [labels.json ...]

With no argument it scores whatever is stored in data/ai/*.json. Each extra
argument is a JSON object mapping game name -> "Low"/"Medium"/"High", so
competing schemes can be scored side by side in one table.
"""
import json, os, sys, glob

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ["Low", "Medium", "High"]


def calls(path=None):
    path = path or os.path.join(HERE, "tests", "interaction_calls.txt")
    out = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for op in ("<=", ">=", "="):
            if op in line:
                name, level = line.split(op, 1)
                out.append((name.strip(), op, level.strip()))
                break
    return out


def ok(op, want, got):
    if got not in ORDER:
        return False
    i, j = ORDER.index(got), ORDER.index(want)
    return i == j if op == "=" else i >= j if op == ">=" else i <= j


def stored():
    games = json.load(open(os.path.join(HERE, "data", "games.json")))
    if isinstance(games, dict):
        games = games.get("games", games)
    out = {}
    for g in games:
        p = os.path.join(HERE, "data", "ai", "%s.json" % g.get("id"))
        if os.path.exists(p):
            ix = json.load(open(p)).get("interaction") or {}
            if ix.get("level"):
                out[g["name"]] = ix["level"]
    return out


def lookup(table, name):
    if name in table:
        return table[name]
    hits = [v for k, v in table.items() if k.startswith(name)]
    return hits[0] if hits else None


def main():
    schemes = [("stored", stored())]
    for path in sys.argv[1:]:
        schemes.append((os.path.basename(path).replace(".json", ""), json.load(open(path))))
    rows = calls()
    width = max(len(n) for n, _, _ in rows)
    head = " " * (width + 12) + "  ".join("%-8s" % n[:8] for n, _ in schemes)
    print(head)
    score = [0] * len(schemes)
    for name, op, want in rows:
        cells = []
        for i, (_, table) in enumerate(schemes):
            got = lookup(table, name)
            good = ok(op, want, got)
            score[i] += good
            cells.append("%-8s" % ("%s%s" % (got or "-", "" if good else " x")))
        print("%-*s %-3s %-7s %s" % (width, name, op, want, "  ".join(cells)))
    print()
    for (label, _), s in zip(schemes, score):
        print("%-12s %d/%d" % (label, s, len(rows)))


if __name__ == "__main__":
    main()
