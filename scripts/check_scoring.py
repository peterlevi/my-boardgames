#!/usr/bin/env python3
"""Check the derived scoring calls against tests/expectations.txt.

    python3 scripts/check_scoring.py

The expectations are the owner's own judgements about games he knows well.
They are never fed into the report — they only say whether the rules in
scripts/scoring.py, fed by the facts the opinion pass collects, agree with a
person who has played these games.
"""
import sys

from common import ROOT, load_games
from scoring import SALAD_ORDER, salad, win

FILE = ROOT / "tests" / "expectations.txt"


def parse():
    want = []
    for raw in FILE.read_text().splitlines():
        line = raw.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        name, rest = line.split(":", 1)
        # Game names contain colons, so split on the last one before a key.
        while rest and not any(rest.strip().startswith(k)
                               for k in ("salad", "win")):
            head, _, rest = rest.partition(":")
            name = f"{name}:{head}"
        checks = {}
        for part in rest.split():
            for op in ("<=", ">=", "="):
                if op in part:
                    key, val = part.split(op, 1)
                    checks[key] = (op, val)
                    break
        want.append((name.strip(), checks))
    return want


def ok(op, got, val):
    if got is None:
        return False
    if op == "=":
        return got == val
    i, j = SALAD_ORDER.index(got), SALAD_ORDER.index(val)
    return i <= j if op == "<=" else i >= j


def main():
    games = {g["name"]: g for g in load_games()}
    passed, failed = 0, []
    for name, checks in parse():
        g = games.get(name)
        if not g:
            failed.append((name, "not in the collection", "", ""))
            continue
        facts = (g.get("ai") or {}).get("scoring") or {}
        got = {"salad": salad(facts), "win": win(facts)}
        for key, (op, val) in checks.items():
            if key == "win":
                good = got["win"] == val
            else:
                good = ok(op, got[key], val)
            if good:
                passed += 1
            else:
                failed.append((name, key, f"{op}{val}", str(got[key])))
    print(f"{passed} checks pass, {len(failed)} fail")
    for name, key, want, got in failed:
        print(f"  {name[:34]:36} {key:6} want {want:10} got {got}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
