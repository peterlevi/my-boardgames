"""Shared helpers: credential loading and repo paths."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def load_creds():
    """Read credentials.env (KEY=VALUE lines); env vars win over the file."""
    creds = {}
    f = ROOT / "credentials.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip()
    for k in ("BGG_USERNAME", "BGG_TOKEN"):
        if os.environ.get(k):
            creds[k] = os.environ[k]
    missing = [k for k in ("BGG_USERNAME", "BGG_TOKEN") if not creds.get(k)]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Copy credentials.env.example to "
            f"credentials.env and fill it in."
        )
    return creds


def load_games():
    """The normalised collection built by build.py."""
    import json
    return json.loads((ROOT / "data" / "games.json").read_text())


def poll_stats(game, n):
    """Aggregate BGG's suggested_numplayers poll for `n` players.

    Returns None when nobody voted at that count. `is_best` means n drew more
    "Best" votes than any other player count for this game.
    """
    d = game["poll"].get(str(n))
    if not d:
        return None
    best, rec, nr = (d.get("Best", 0), d.get("Recommended", 0),
                     d.get("Not Recommended", 0))
    total = best + rec + nr
    if total == 0:
        return None
    top = max((v.get("Best", 0) for v in game["poll"].values()), default=0)
    return dict(best=best, total=total, best_pct=100 * best / total,
                approval=100 * (best + rec) / total,
                is_best=(best == top and best > 0))


def load_exclusions(path):
    """Names to drop, one per line; blank lines and # comments ignored."""
    if not path:
        return set()
    names = set()
    for line in (ROOT / path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(line)
    return names


def load_overrides(path):
    """`Name = Level` lines; blanks and # comments ignored."""
    f = ROOT / path
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text().splitlines():
        line = line.split("#")[0].strip()
        if "=" in line:
            name, level = line.split("=", 1)
            out[name.strip()] = level.strip()
    return out


def add_filter_args(ap, default_players=4):
    """The filter flags shared by query.py and report.py."""
    ap.add_argument("--players", type=int, default=default_players)
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
    ap.add_argument("--tag", action="append", default=[], metavar="NAME",
                    help="require a BGG mechanic or category; repeatable")
    ap.add_argument("--expansions", choices=["drop", "show"], default="drop",
                    help="expansions are listed as their own rows, or not "
                         "(default: not, matching the report)")
    return ap


def select(a):
    """Apply the shared filters, returning [(game, stats)] sorted by BGG rank
    ascending with unranked entries last."""
    excluded = load_exclusions(a.exclude_file)
    rows = []
    for g in load_games():
        if g["is_expansion"] and getattr(a, "expansions", "drop") != "show":
            continue
        # --players 0 means "any count", matching the report; the poll filters
        # then do not apply at all.
        s = poll_stats(g, a.players) if a.players else None
        if a.players:
            if not s or s["total"] < a.min_votes:
                continue
            if not (s["is_best"] or s["best_pct"] >= a.min_best):
                continue
            if s["approval"] < a.min_approval:
                continue
        if g["name"] in excluded:
            continue
        tags = set(g["mechanics"]) | set(g["categories"])
        if any(t not in tags for t in getattr(a, "tag", [])):
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
    return rows


def playtime(game):
    lo, hi = game["minplaytime"], game["maxplaytime"]
    return str(lo) if lo == hi else f"{lo}–{hi}"
