#!/usr/bin/env python3
"""Build a local opinion database for the collection using the `claude` CLI.

    python3 scripts/enrich.py              # only games without a cached answer
    python3 scripts/enrich.py --force      # redo everything
    python3 scripts/enrich.py --limit 5    # try a handful first
    python3 scripts/enrich.py --jobs 6     # parallel calls (default 4)
    python3 scripts/enrich.py --batch 1    # one game per call (slower, finer)
    python3 scripts/enrich.py --describe   # second pass over unknown games
    python3 scripts/enrich.py --online     # look the unknown ones up on the web

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
empty panel. Two passes fill it, in increasing order of cost.

`--describe` asks a narrower question of the same offline model — describe how
this plays *from the rulebook text supplied*, and say nothing about reception.
Marked `"source": "description"`.

`--online` actually goes and looks, giving the model WebSearch and WebFetch.
This is the right answer for recent games, where training data is simply
absent rather than vague: asked about Daitoshi it found the game is Devir's
2024 title by Dani García, part of the Kemushi Saga, and returned sourced
praise and criticism. Batch size matters enormously here. One game per call measured at $0.60,
because the agent loop's fixed overhead — system prompt, tool definitions,
accumulated search context — dominates a single lookup. Five games in one call
measured at $0.338, or $0.068 each: nearly ten times cheaper for the same
work. So --online batches by default, and the whole collection would cost
around $16 rather than $145. Marked `"source": "web"`, with the pages it used
stored alongside.

The subprocess gets web tools and is explicitly denied Bash, Write and Edit.
Permission prompts have to be bypassed for a non-interactive run, so the
denial list is what keeps an unattended loop from doing anything but read.
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
# What the run has cost so far, one entry per claude call.
SPEND = []
SCHEMA_VERSION = 3


FACTS_BRIEF = """
Scoring facts, reported rather than judged — the labels are worked out from
these afterwards, so give what the rules say and nothing more:

  "subsystems": the separate scoring engines a player builds up, each with its
      own rules and economy. Most games have one or two; be honest rather than
      generous. Carcassonne scores cities, roads, monasteries and
      farms, but they all come from placing a tile and a meeple: that is ONE
      subsystem, not four. Rajas of the Ganges really does run several
      minigames side by side. Name them; do not pad the list.
  "sources": the categories the rules total at the end, named.
  "winning_score": what a winning score typically looks like, as a plain
      number (10 for a race to 10, about 165 for Brass).
  "tally": "running" if the score ticks along in front of everyone,
      "endgame" if almost all of it is counted at the end, else "mixed".
  "shape": "single_currency" when one currency decides it (money in Food Chain
      Magnate), "objective_count" when you count achievements or objectives,
      "lowest_category" when your score is your weakest category (Tigris &
      Euphrates), "majority_control" when players contest shared majorities
      rather than accumulating, else "sum".
  "ends_by": how the game ENDS and who that leaves winning.
      "target_score" — reaching a number ends it and that player has won;
      "end_trigger" — someone completing something stops the game, but the
          points still decide it (Azul's finished row, Wingspan's rounds);
      "fixed_length" — a set number of rounds;
      "exhaustion" — a deck or supply runs out;
      "sudden_death" — a condition wins outright, there and then, without
          counting anything (7 Wonders Duel's military or science supremacy);
      "elimination"; or "coop_goal".
  "sudden_death_common": true only where such a condition exists AND games
      usually end that way rather than going the distance.
"""

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
  "scoring": {{
    "subsystems": ["..."],
    "sources": ["..."],
    "winning_score": 0,
    "tally": "running" | "endgame" | "mixed",
    "shape": "sum" | "single_currency" | "objective_count" | \
"lowest_category" | "majority_control",
    "ends_by": "target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal",
    "sudden_death_common": false,
    "how_you_win": "one or two sentences on how a player actually wins, in \
plain language"
  }},
  "similar": ["3-5 games liked by people who like this one"],
  "teachers": ["2-3 YouTube channels that are known for teaching this kind of \
game and plausibly cover this one — name the channel only, e.g. Watch It \
Played, Rahdo Runs Through, JonGetsGames, Before You Play. Never invent a \
video title or URL."]
}}

{rule}
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


ONLINE = """Search the web for each game below and report what players \
actually say about it. Use BoardGameGeek, reviews and forum threads. The BGG \
data given may be thin or wrong — trust what you find over what is supplied, \
and over anything you half-remember.

Answer ONLY with a JSON object mapping each id to:
{{
  "confidence": "high" | "medium" | "low",
  "summary": "two sentences on what playing it is actually like",
  "praised": ["what people consistently like", "..."],
  "criticised": ["what people consistently dislike", "..."],
  "interaction": {{
    "level": "Low" | "Medium" | "High",
    "kind": "a few words",
    "detail": "two or three sentences on how players affect each other and \
how much of the state is shared versus each player's own board"
  }},
  "scoring": {{
    "subsystems": ["..."], "sources": ["..."], "winning_score": 0,
    "tally": "running" | "endgame" | "mixed",
    "shape": "sum" | "single_currency" | "objective_count" | \
"lowest_category" | "majority_control",
    "ends_by": "target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal",
    "sudden_death_common": false,
    "how_you_win": "one or two sentences"
  }},
  "similar": ["3-5 games"],
  "sources": ["the pages you actually used"]
}}

If the search genuinely turns up nothing, say so with "confidence": "low" and \
empty fields. Never pad the answer out with plausible invention.
{rule}
GAMES:
"""


RESCORE_WEB = """Look each game's rules up on the web before answering — \
BoardGameGeek's page, the rulebook, a review that states the numbers. Do not \
answer the ending or the winning score from memory. Add "checked": ["url", \
...] to every entry naming the pages you actually read for those two fields.

"""

RESCORE = """For each game below, report only how its scoring works. Use what \
you know about the game, reconciled with the BGG data given. Answer ONLY with \
a JSON object mapping each id to:
{{
  "scoring": {{
    "subsystems": ["..."],
    "sources": ["..."],
    "winning_score": 0,
    "tally": "running" | "endgame" | "mixed",
    "shape": "sum" | "single_currency" | "objective_count" | \
"lowest_category" | "majority_control",
    "ends_by": "target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal",
    "sudden_death_common": false,
    "how_you_win": "one or two sentences on how a player actually wins, in \
plain language"
  }}
}}
{rule}
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
    head = header or HEADER.format(rule=FACTS_BRIEF)
    return head + body


def fingerprint(g):
    """Cache key: redo a game only when the inputs or the schema change."""
    basis = json.dumps([SCHEMA_VERSION, g["name"], g["year"], g["mechanics"],
                        g["categories"], (g["description"] or "")[:1200]],
                       sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def ask(prompt, model, online=False):
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if online:
        cmd += ["--allowedTools", "WebSearch", "WebFetch",
                # A non-interactive run cannot answer prompts, so the gate has
                # to come down; this list is what stops it doing anything but
                # read the web.
                "--disallowedTools", "Bash", "Write", "Edit", "NotebookEdit",
                "--permission-mode", "bypassPermissions"]
    # Without an explicit /dev/null the CLI waits on stdin and then warns
    # about it, which lands in the output and breaks the JSON parse.
    r = subprocess.run(cmd, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL,
                       timeout=600 if online else 240)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-300:])
    envelope = json.loads(r.stdout)
    cost = envelope.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        SPEND.append(cost)
    text = envelope.get("result", "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def process(batch, model, describe=False, online=False, rescore=False):
    # --rescore --online asks only for the scoring facts, but with the web
    # open: the rules of a game are written down somewhere, and a fact the
    # model half-remembers is exactly the case worth looking up.
    header = ((RESCORE_WEB if online else "") + RESCORE.format(rule=FACTS_BRIEF)
              if rescore
              else ONLINE.format(rule=FACTS_BRIEF) if online
              else DESCRIBE if describe else None)
    answers = ask(prompt_for(batch, header), model, online=online)
    written = []
    for g in batch:
        data = answers.get(str(g["id"])) or answers.get(g["id"])
        if not isinstance(data, dict):
            continue
        if online:
            data["source"] = "web"
        if rescore:
            # Only the scoring facts are re-asked; everything else in the
            # entry — summary, praise, interaction, sources — stands.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            existing.pop("win_criteria", None)
            facts = data.get("scoring") or {}
            if facts:
                existing["scoring"] = facts
            data = existing
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
    ap.add_argument("--online", action="store_true",
                    help="look entries up on the web (slow, costs real money)")
    ap.add_argument("--only", metavar="IDS",
                    help="comma-separated game ids, for retrying the handful "
                         "a failed batch left behind")
    ap.add_argument("--rescore", action="store_true",
                    help="re-ask only win_criteria and scoring for every "
                         "cached entry, leaving the rest of it alone")
    a = ap.parse_args()

    if not shutil.which("claude"):
        print("`claude` is not on PATH — skipping enrichment. "
              "Everything else works without it.")
        return

    AI.mkdir(parents=True, exist_ok=True)
    only = {i.strip() for i in a.only.split(",")} if a.only else None
    todo = []
    for g in load_games():
        if g["is_expansion"]:
            continue
        if only and str(g["id"]) not in only:
            continue
        cached = AI / f'{g["id"]}.json'
        if a.rescore:
            if cached.exists():
                todo.append(g)
            continue

        if a.describe or a.online:
            # Only entries the first pass could not speak to.
            if not cached.exists():
                continue
            try:
                d = json.loads(cached.read_text())
            except Exception:  # noqa: BLE001
                continue
            weak = d.get("confidence") == "low" or d.get("source") == "description"
            if a.force or (weak and d.get("source") != "web"):
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
    if a.online:
        # Measured at ~$0.068/game in batches of five; a lone game costs
        # nearly ten times that, so the batch size is doing real work.
        print(f"WEB LOOKUP: {len(todo)} game(s), roughly "
              f"${0.07 * len(todo):.2f}", flush=True)
    print(f"enriching {len(todo)} game(s) with {a.model}: "
          f"{len(batches)} calls of {a.batch}, {a.jobs} at a time", flush=True)

    done = failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = {pool.submit(process, b, a.model, a.describe,
                               a.online, a.rescore): b
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
    spent = sum(SPEND)
    money = f", ${spent:.2f} spent" if spent else ""
    print(f"done: {done} enriched, {failed} failed{money}")


if __name__ == "__main__":
    main()
