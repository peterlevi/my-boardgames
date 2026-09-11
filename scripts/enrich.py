#!/usr/bin/env python3
"""Build a local opinion database for the collection using the `claude` CLI.

    python3 scripts/enrich.py              # only games without a cached answer
    python3 scripts/enrich.py --force      # redo everything
    python3 scripts/enrich.py --limit 5    # try a handful first
    python3 scripts/enrich.py --jobs 6     # parallel calls (default 4)

Optional by design. If `claude` is not on PATH the script says so and exits 0,
and every other script keeps working — the enrichment only ever adds columns.

Each answer is cached at data/ai/<id>.json and committed, so a resync only
pays for genuinely new games, and anyone who clones the repo gets the whole
database for free without running this at all.

Two things keep the answers honest:

* Every prompt is **grounded** in the cached BGG data — description, mechanics,
  categories, weight, player-count poll. The model is asked to reconcile what
  it knows with what is in front of it rather than recall alone, which is what
  makes this work for games published after its training cutoff.
* The schema carries `confidence`. A game the model does not actually know
  should come back `low` with empty opinion fields rather than a confident
  invention, and the report can then show nothing rather than a fabrication.
"""
import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import sys

from common import ROOT, load_games

AI = ROOT / "data" / "ai"
SCHEMA_VERSION = 1

WIN_CRITERIA = [
    "Most points, many sources", "Most points, one or two sources",
    "Most money", "Race to a finish", "Lowest-highest scoring",
    "Special win condition", "Cooperative goal", "Other",
]

PROMPT = """You are cataloguing a board game collection. Answer ONLY with a \
JSON object, no prose, no code fence.

Use what you know about how this game is actually received and played. \
Reconcile it with the BGG data below — if you do not recognise the game, say \
so with "confidence": "low" and leave the opinion fields empty rather than \
guessing.

GAME: {name} ({year})
DESIGNERS: {designers}
BGG WEIGHT: {weight}/5   PLAYERS: {players}   TIME: {time} min
CATEGORIES: {categories}
MECHANICS: {mechanics}
BGG DESCRIPTION: {description}

Return exactly this shape:
{{
  "confidence": "high" | "medium" | "low",
  "summary": "two sentences on what playing it is actually like",
  "praised": ["what people consistently like", "..."],
  "criticised": ["what people consistently dislike", "..."],
  "interaction": {{
    "level": "Low" | "Medium" | "High",
    "kind": "a few words: e.g. blocking and area denial, open conflict, \
trading and negotiation, mostly parallel play"
  }},
  "win_criteria": one of {criteria},
  "scoring": {{
    "breadth": "Focused" | "Some" | "Broad" | "Salad",
    "why": "one sentence on what actually decides the winner"
  }},
  "similar": ["3-5 games liked by people who like this one"]
}}"""


def prompt_for(g):
    return PROMPT.format(
        name=g["name"], year=g["year"] or "?",
        designers=", ".join(g["designers"]) or "unknown",
        weight=f'{g["weight"]:.2f}' if g["weight"] else "?",
        players=f'{g["minplayers"]}-{g["maxplayers"]}',
        time=f'{g["minplaytime"]}-{g["maxplaytime"]}',
        categories=", ".join(g["categories"]) or "none listed",
        mechanics=", ".join(g["mechanics"]) or "none listed",
        description=(g["description"] or "")[:1200],
        criteria=json.dumps(WIN_CRITERIA),
    )


def fingerprint(g):
    """Cache key: redo a game only when the inputs or the schema change."""
    basis = json.dumps([SCHEMA_VERSION, g["name"], g["year"], g["mechanics"],
                        g["categories"], (g["description"] or "")[:1200]],
                       sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def ask(prompt, model):
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json",
         "--model", model],
        capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-300:])
    envelope = json.loads(r.stdout)
    text = envelope.get("result", "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def process(g, model):
    out = AI / f'{g["id"]}.json'
    data = ask(prompt_for(g), model)
    data["_fingerprint"] = fingerprint(g)
    data["_name"] = g["name"]
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return g["name"], data.get("confidence", "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="claude-sonnet-5")
    a = ap.parse_args()

    if not shutil.which("claude"):
        print("`claude` is not on PATH — skipping enrichment. "
              "Everything else works without it.")
        return

    AI.mkdir(parents=True, exist_ok=True)
    todo = []
    for g in load_games():
        if g["is_expansion"]:
            continue
        cached = AI / f'{g["id"]}.json'
        if cached.exists() and not a.force:
            try:
                if json.loads(cached.read_text()).get("_fingerprint") == fingerprint(g):
                    continue
            except Exception:
                pass
        todo.append(g)
    if a.limit:
        todo = todo[:a.limit]

    if not todo:
        print("nothing to enrich — every game is cached and current")
        return
    print(f"enriching {len(todo)} game(s) with {a.model}, {a.jobs} at a time")

    done = failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = {pool.submit(process, g, a.model): g for g in todo}
        for f in concurrent.futures.as_completed(futures):
            g = futures[f]
            try:
                name, conf = f.result()
                done += 1
                print(f"  [{done + failed}/{len(todo)}] {name} ({conf})")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [{done + failed}/{len(todo)}] {g['name']} FAILED: {e}",
                      file=sys.stderr)
    print(f"done: {done} enriched, {failed} failed")


if __name__ == "__main__":
    main()
