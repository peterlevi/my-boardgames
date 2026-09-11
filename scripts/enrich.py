#!/usr/bin/env python3
"""Build a local opinion database for the collection using the `claude` CLI.

    python3 scripts/enrich.py              # only games without a cached answer
    python3 scripts/enrich.py --force      # redo everything
    python3 scripts/enrich.py --limit 5    # try a handful first
    python3 scripts/enrich.py --jobs 6     # parallel calls (default 4)
    python3 scripts/enrich.py --batch 1    # one game per call (slower, finer)
    python3 scripts/enrich.py --describe   # second pass over unknown games

Optional by design. If `claude` is not on PATH the script says so and exits 0,
and every other script keeps working — the enrichment only ever adds columns.

Each answer is cached at data/ai/<id>.json and committed, so a resync only
pays for genuinely new games, and anyone who clones the repo gets the whole
database for free without running this at all.

Games are asked about in batches. Each `claude` invocation boots a whole agent
session, and that startup — not the thinking — dominates: one game per call
measured at roughly 100 minutes for this collection, where eight per call
takes minutes. The batch is small enough that the answers stay specific.

Two things keep the answers honest:

* Every prompt is **grounded** in the cached BGG data — description, mechanics,
  categories, weight, player-count poll. The model is asked to reconcile what
  it knows with what is in front of it rather than recall alone, which is what
  makes this work for games published after its training cutoff.
* The schema carries `confidence`. A game the model does not actually know
  should come back `low` with empty opinion fields rather than a confident
  invention, and the report can then show nothing rather than a fabrication.

That honesty leaves a gap: an obscure or very recent game ends up with an
empty panel. `--describe` is a second pass over exactly those entries that
asks a narrower question — describe how this plays *from the rulebook text
supplied*, and say nothing about reception. The result is marked
`"source": "description"` so the report can label it as read off the
description rather than drawn from what players think.
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
SCHEMA_VERSION = 2

WIN_CRITERIA = [
    "Most points, many sources", "Most points, one or two sources",
    "Most money", "Race to a finish", "Lowest-highest scoring",
    "Special win condition", "Cooperative goal", "Other",
]

HEADER = """You are cataloguing a board game collection. Answer ONLY with a \
JSON object mapping each game's id to its entry. No prose, no code fence.

For each game use what you know about how it is actually received and played, \
reconciled with the BGG data given. If you do not recognise a game, set \
"confidence": "low" and leave the opinion fields empty rather than guessing — \
an honest gap is worth more here than a plausible invention.

Entry shape, for every id below:
{{
  "confidence": "high" | "medium" | "low",
  "summary": "two sentences on what playing it is actually like",
  "praised": ["what people consistently like", "..."],
  "criticised": ["what people consistently dislike", "..."],
  "interaction": {{
    "level": "Low" | "Medium" | "High",
    "kind": "a few words, e.g. blocking and area denial, open conflict, \
trading and negotiation, mostly parallel play",
    "detail": "two or three sentences: through what actions players actually \
affect each other, and how much of the game state is shared versus each \
player's own board or tableau"
  }},
  "win_criteria": one of {criteria},
  "scoring": {{
    "breadth": "Focused" | "Some" | "Broad" | "Salad",
    "why": "one sentence on what actually decides the winner",
    "how_you_win": "one or two sentences on how a player actually wins, in \
plain language"
  }},
  "similar": ["3-5 games liked by people who like this one"],
  "teachers": ["2-3 YouTube channels that are known for teaching this kind of \
game and plausibly cover this one — name the channel only, e.g. Watch It \
Played, Rahdo Runs Through, JonGetsGames, Before You Play. Never invent a \
video title or URL."]
}}

GAMES:
"""

ENTRY = """
--- id {id}
NAME: {name} ({year})
DESIGNERS: {designers}
BGG WEIGHT: {weight}/5   PLAYERS: {players}   TIME: {time} min
CATEGORIES: {categories}
MECHANICS: {mechanics}
DESCRIPTION: {description}
"""


DESCRIBE = """These games were not recognised well enough to describe what \
players think of them. Do not try. Instead describe how each one *plays*, \
using only the BGG text supplied — mechanics, flow, and what the scoring \
rewards. Say nothing about reception, quality, or what people like.

Answer ONLY with a JSON object mapping each id to:
{{
  "summary": "two sentences on how a game of this actually goes",
  "interaction": {{
    "level": "Low" | "Medium" | "High",
    "kind": "a few words",
    "detail": "two sentences on how players affect each other and how much of \
the state is shared versus each player's own board"
  }},
  "scoring": {{
    "how_you_win": "one or two sentences on how a player wins"
  }}
}}

GAMES:
"""


def prompt_for(batch, header=None):
    body = "".join(
        ENTRY.format(
            id=g["id"], name=g["name"], year=g["year"] or "?",
            designers=", ".join(g["designers"]) or "unknown",
            weight=f'{g["weight"]:.2f}' if g["weight"] else "?",
            players=f'{g["minplayers"]}-{g["maxplayers"]}',
            time=f'{g["minplaytime"]}-{g["maxplaytime"]}',
            categories=", ".join(g["categories"]) or "none listed",
            mechanics=", ".join(g["mechanics"]) or "none listed",
            description=(g["description"] or "")[:700],
        ) for g in batch)
    head = header or HEADER.format(criteria=json.dumps(WIN_CRITERIA))
    return head + body


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


def process(batch, model, describe=False):
    answers = ask(prompt_for(batch, DESCRIBE if describe else None), model)
    written = []
    for g in batch:
        data = answers.get(str(g["id"])) or answers.get(g["id"])
        if not isinstance(data, dict):
            continue
        if describe:
            # Fill only the blanks; the structural fields from the first pass
            # stay as they were, and the panel gets labelled as descriptive.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            existing["summary"] = data.get("summary", "")
            existing["interaction"].update(
                {k: v for k, v in (data.get("interaction") or {}).items() if v})
            existing["scoring"]["how_you_win"] = \
                (data.get("scoring") or {}).get("how_you_win", "")
            existing["source"] = "description"
            data = existing
        data["_fingerprint"] = fingerprint(g)
        data["_name"] = g["name"]
        (AI / f'{g["id"]}.json').write_text(
            json.dumps(data, indent=1, ensure_ascii=False))
        written.append(g["name"])
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=8,
                    help="games per claude call (CLI startup dominates)")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--describe", action="store_true",
                    help="second pass over low-confidence entries")
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
        if a.describe:
            # Only entries the first pass could not speak to.
            if not cached.exists():
                continue
            try:
                d = json.loads(cached.read_text())
            except Exception:  # noqa: BLE001
                continue
            if d.get("confidence") == "low" and not d.get("source"):
                todo.append(g)
            continue
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
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"enriching {len(todo)} game(s) with {a.model}: "
          f"{len(batches)} calls of {a.batch}, {a.jobs} at a time", flush=True)

    done = failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = {pool.submit(process, b, a.model, a.describe): b
                   for b in batches}
        for f in concurrent.futures.as_completed(futures):
            batch = futures[f]
            try:
                written = f.result()
                done += len(written)
                failed += len(batch) - len(written)
                print(f"  {done + failed}/{len(todo)} — {', '.join(written[:3])}"
                      + ("…" if len(written) > 3 else ""), flush=True)
            except Exception as e:  # noqa: BLE001
                failed += len(batch)
                print(f"  batch FAILED ({batch[0]['name']}…): {e}",
                      file=sys.stderr, flush=True)
    print(f"done: {done} enriched, {failed} failed")


if __name__ == "__main__":
    main()
