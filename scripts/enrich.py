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
import time
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
  "sources": every line you would write on a scorepad, named — be exhaustive
      rather than tidy. Brass really does have two (links, industries); a
      middleweight euro usually has four to eight, and leaving some out is the
      single most common way to get this wrong.
  "winning_score": what a winning score typically looks like, as a plain
      number (10 for a race to 10, about 165 for Brass).
  "tally": "running" if the score ticks along in front of everyone,
      "endgame" if almost all of it is counted at the end, else "mixed".
  "shape": "single_currency" when one currency decides it (money in Food Chain
      Magnate), "objective_count" when you count achievements or objectives,
      "lowest_category" when your score is your weakest category (Tigris &
      Euphrates), "majority_control" when players contest shared majorities
      rather than accumulating, else "sum".
  "ends_by": how the game ENDS and who that leaves winning — a LIST, most
      common first, because plenty of games have more than one ending.
      Innovation is won either by claiming enough achievements or by a special
      achievement; 7 Wonders Duel by military or science supremacy, or on
      points if neither lands. Use these values:
      "target_score" — reaching a number ends it and that player has won;
      "end_trigger" — someone completing something stops the game, but the
          points still decide it (Azul's finished row, Wingspan's rounds);
      "fixed_length" — a set number of rounds;
      "exhaustion" — a deck or supply runs out;
      "sudden_death" — a condition wins outright, there and then, without
          counting anything;
      "elimination"; or "coop_goal".
      List only endings the rules really have, at most three.
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
    "ends_by": ["target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal"],
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
    "ends_by": ["target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal"],
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


INTERACTION_WEB = """Search for each game before answering — BoardGameGeek \
forum threads and reviews are the best source; the game name plus \
"interaction", "multiplayer solitaire", "cutthroat" or "mean" finds the \
argument quickly. Rate what players actually report, not what the box \
suggests, and add "checked": ["url", ...] to every entry naming the pages you
read.

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
    "ends_by": ["target_score" | "end_trigger" | "fixed_length" | \
"exhaustion" | "sudden_death" | "elimination" | "coop_goal"],
    "how_you_win": "one or two sentences on how a player actually wins, in \
plain language"
  }}
}}
{rule}
GAMES:
"""


ENDINGS = """For each game below, list every way it can END and who that \
leaves winning — most common first, at most three. Plenty of games have two or \
three: Innovation is won by claiming enough achievements, or outright by a \
special achievement, or on points when the draw pile runs dry.

Answer ONLY with a JSON object mapping each id to:
{{
  "endings": [
    {{
      "how": "target_score" | "end_trigger" | "fixed_length" | "exhaustion" \
| "sudden_death" | "elimination" | "coop_goal",
      "decided_by": "points" | "money" | "objectives" | "majority" | \
"lowest" | "instant"
    }}
  ]
}}

"how" is what stops the game: reaching a number, someone completing \
something, a set number of rounds, a deck running out, a condition that wins \
on the spot, elimination, or the players' shared goal. "decided_by" is what \
then settles it: the highest total, the most money, a count of objectives, \
control of contested majorities, your weakest category, or nothing further \
because that condition won outright.

GAMES:
"""


SOURCES = """For each game below, list the distinct CATEGORIES the rules score \
— not every line of the scorepad.

Count a category once however many times it is scored: Brass scores links and \
industries in each of two eras, and that is two categories, not four. Ignore \
optional variants and expansion modules; describe the game as it comes in the \
box and is usually played. A conversion of leftovers into points at the end \
(spare money, unused resources) is not a category of its own.

Answer ONLY with a JSON object mapping each id to:
{{
  "sources": ["...", "..."]
}}

GAMES:
"""


SCORES = """For each game below, give the range a winning score typically \
falls in — the number the winner actually ends on, not the maximum possible.

If the players keep a score at all, give the range — even when the game can \
also end some other way, and even when the score is a fixed target (Catan's \
ten points ARE its winning score, 7 Wonders Duel's sixty-odd count even \
though a supremacy can end it early). Leave it null ONLY when nobody counts \
anything: a pure cooperative goal, a last-player-standing fight, a game \
decided solely by a condition with no score behind it.

If the range differs by player count in a way worth knowing, say so in "note" \
in a handful of words; otherwise leave "note" empty.

Answer ONLY with a JSON object mapping each id to:
{{
  "score_range": [low, high] | null,
  "note": ""
}}

GAMES:
"""


THEME = """For each game below, judge how tightly its mechanics fit its \
theme — whether the rules model the subject, or whether the subject is a \
label on a structure that could have been about anything.

The question is ONLY about the rules. It is not about whether the theme is \
serious, beautiful, well produced, or heavily written. A silly or joke theme \
can fit its mechanics perfectly; a lavish, lore-heavy production can be a \
generic engine underneath. Judge what the rules do.

The test that settles it: would somebody who knows the real subject recognise \
the rules as a model of it, and be able to predict what they do? If yes, the \
fit is high, however daft the setting. If the rules would work unchanged with \
every noun replaced, the fit is low, however rich the setting.

Work in this order, and do not pick the number until the last step.

1. "said": what do experienced players say about this game's theme, in their \
words — "pasted-on theme", "could be about anything", "abstract with a skin", \
"the theme drips off it", "the mechanics ARE the theme"? Report the phrases, \
but weigh them carefully, because players use "pasted on" loosely: very often \
they mean the theme is thin, silly or unserious, which is a comment about \
tone, not about mechanical fit. Only count such a phrase as evidence when it \
is plainly about the RULES not matching the subject. If you do not know the \
game's reputation, begin this field with "unknown".
2. "why": one sentence naming the clearest rule either way — a rule that only \
makes sense because of the subject, or a rule that plainly does not care what \
the subject is.
3. "fit": an integer 0-100. Use the whole range; do not round to tens.

  0-20   the theme is a coat of paint. Renaming every component would cost \
the game nothing. Most abstracts and many classic euros live here: an \
area-majority game where the regions could be anything, a network game where \
the goods could be anything.
  21-40  evocative but decorative: the subject suggests the components and \
the art, not the rules.
  41-60  some rules clearly come from the subject; others are generic \
scaffolding bolted alongside them.
  61-80  most rules are recognisably about the subject, and knowing the \
subject helps you play.
  81-100 the mechanics could not be about anything else. The rules simulate \
the subject closely enough that understanding the subject teaches you the \
game.

Two worked examples of the distinction, to calibrate against. A game about \
running fast-food chains where you hire and train staff, where marketing \
creates demand in specific neighbourhoods, where you undercut rivals on price \
and must pay every employee's wage whether or not they produced anything, is \
a HIGH fit — that is how the business actually works, and the cartoon art \
does not change it. A game about medieval merchants whose rules are a pure \
network-and-majority puzzle, where the goods and cities are interchangeable \
counters, is a LOW fit however historical the setting.

Answer ONLY with a JSON object mapping each id to:
{{
  "theme": {{
    "said": "the recurring phrases, or unknown",
    "why": "one sentence",
    "fit": 0-100
  }}
}}

GAMES:
"""


STYLE = """For each game below, place it on the euro-to-ameritrash axis that \
players argue about.

Work in this order, and do not pick the number until the last step.

1. "said": how does the community actually describe this game — "classic \
euro", "point salad euro", "euro-game", "ameritrash", "dudes on a map", \
"thematic game", "euro-trash hybrid", "war game"? If you do not know, begin \
with "unknown" and reason from the rules below.
2. "why": one sentence naming the features that place it — the things that \
actually decide this are direct conflict, how much randomness resolves \
important moments, whether players can be eliminated or badly damaged by \
others, whether powers are asymmetric, and whether the rules serve a story or \
an economy.
3. "style": an integer 0-100.

  0-20   pure euro: no direct conflict, little or no luck after setup, \
indirect competition through shared markets and actions, everyone symmetric, \
the game ends on a fixed trigger and points decide it.
  21-40  euro with an edge: blocking, a shared map, or modest randomness, but \
still an economy first.
  41-60  genuine hybrid: a euro economy carrying real conflict or real \
swings, or a thematic game with tight euro scaffolding.
  61-80  ameri-leaning: direct attacks, dice or cards resolving key moments, \
asymmetric powers, a narrative arc.
  81-100 full ameritrash: player elimination or crushing attacks, big \
randomness, miniatures and story, the experience matters more than the \
optimisation.

Do not use weight, length or table size as evidence — heavy does not mean \
euro, long does not mean ameritrash.

Answer ONLY with a JSON object mapping each id to:
{{
  "style": {{
    "said": "the recurring phrases, or unknown",
    "why": "one sentence",
    "style": 0-100
  }}
}}

GAMES:
"""


# Interaction is the one axis where asking for a label works, but only if the
# evidence is demanded first. Four schemes were scored against the owner's own
# calls for 26 games (tests/interaction_calls.txt, scripts/check_interaction.py):
# a calibrated judgement 21/26, "what does the community say" 21/26, a web
# search with citations 21/26 at ten times the price, and this one — say what
# players call the game, then name the mechanism, then commit to a level —
# 22/26 for the same ~$0.013 a game. Ordering is the whole difference: asked
# for a level first, the model reasons from weight and table presence and rates
# every heavy euro High. Asked for the phrase first, it reaches for
# "multiplayer solitaire" or "cutthroat", and the phrase is usually right.
#
# The remaining misses are not really errors. They are the games where the
# quoted phrase is genuinely the community's and the owner disagrees with it:
# everyone calls Scythe and Patchwork multiplayer solitaire except him. No
# amount of grounding fixes that, which is why the web pass bought nothing.
INTERACTION = """For each game below, rate how much the players' games \
touch each other in practice — how often what one player does changes what \
another can do or score.

Work in this order, and do not decide the level until the last step. What \
players SAY about a game is the evidence; the mechanics are only the fallback \
when nobody has said anything.

1. "said": what do experienced players actually say about interaction in this \
game, in their words? Quote the phrases that recur in reviews and forum \
threads — "multiplayer solitaire", "cutthroat", "take-that", "you can't \
really stop anyone", "brutal blocking", "a race you watch", "mean". When the \
recurring praise or complaint is specifically about interaction, that is the \
strongest evidence there is. If you do not know the game's reputation, begin \
this field with "unknown" and fall back on the mechanics listed below.
2. "kind": the one thing through which players most affect each other, in a \
few words — e.g. bidding against each other, blocking spots on a shared map, \
mostly parallel engine building.
3. "level": Low, Medium or High, following what you wrote above.

  High — players routinely and directly affect each other: bidding against \
each other in an auction, taking the exact thing an opponent needed, \
attacking, blocking a key spot, fighting over the same space, negotiating. A \
game where a good move is often chosen BECAUSE of what it denies someone \
else. Games players call "cutthroat" or "mean" belong here.
  Medium — real competition over shared things (a common market, limited \
action spaces, area majorities), but most of a turn is spent building your \
own position.
  Low — you mostly play your own game on your own board; the shared parts are \
a refilling market or a race you watch rather than fight over. Games players \
call "multiplayer solitaire" belong here.

Two traps, and they pull in opposite directions. A heavy euro sprawling over \
a big shared map is often Low despite its table presence, because the players \
are optimising in parallel and the map is scenery. An auction or trick-taking \
game with no board at all is High, because every bid is aimed at an opponent. \
Weight, table size, playing time and theme are not evidence. A war theme \
whose armies rarely meet is not High.

Answer ONLY with a JSON object mapping each id to:
{{
  "interaction": {{
    "said": "the recurring phrases players use, or unknown",
    "kind": "a few words on what the interaction is",
    "level": "Low" | "Medium" | "High",
    "detail": "two or three sentences: through what actions players actually \
affect each other, and how much of the game state is shared versus each \
player's own board"
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
    head = header or HEADER.format(rule=FACTS_BRIEF)
    return head + body


def fingerprint(g):
    """Cache key: redo a game only when the inputs or the schema change."""
    basis = json.dumps([SCHEMA_VERSION, g["name"], g["year"], g["mechanics"],
                        g["categories"], (g["description"] or "")[:1200]],
                       sort_keys=True)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def _extract(text):
    """The model's answer as a dict, tolerating the wrappers it sometimes adds.

    Three of them show up in practice: a ```json fence, a sentence of preamble
    before the object, and a trailing "Let me know if..." after it. Slicing
    from the first brace to the last is enough for all three, and is still
    strict about what is between them.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer: %r" % text[:200])
    return json.loads(text[start:end + 1])


def ask(prompt, model, online=False, tries=3):
    """One `claude` call, retried when the answer comes back unusable.

    Empty answers are not rare enough to ignore: a full-collection pass
    measured 25 of 242 batches returning an empty `result`, which the caller
    used to report as a failed batch and skip. Skipping is the worst outcome
    available, because --force then silently leaves those games on whatever an
    earlier, differently-prompted pass had said, and the database quietly
    becomes a mixture of schemes. A retry costs one more call and fixes almost
    all of them.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if online:
        cmd += ["--allowedTools", "WebSearch", "WebFetch",
                # A non-interactive run cannot answer prompts, so the gate has
                # to come down; this list is what stops it doing anything but
                # read the web.
                "--disallowedTools", "Bash", "Write", "Edit", "NotebookEdit",
                "--permission-mode", "bypassPermissions"]
    last = None
    for attempt in range(tries):
        if attempt:
            time.sleep(2 ** attempt)
        # Without an explicit /dev/null the CLI waits on stdin and then warns
        # about it, which lands in the output and breaks the JSON parse.
        r = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL,
                           timeout=600 if online else 240)
        if r.returncode != 0:
            last = RuntimeError((r.stderr or r.stdout)[-300:])
            continue
        try:
            envelope = json.loads(r.stdout)
        except ValueError as e:
            last = e
            continue
        cost = envelope.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            SPEND.append(cost)
        # An error envelope carries its reason in `result` — "Not logged in",
        # a usage limit — and retrying an empty one is pointless noise.
        if envelope.get("is_error"):
            raise RuntimeError(str(envelope.get("result"))[:200])
        try:
            return _extract(envelope.get("result") or "")
        except ValueError as e:
            last = e
    raise last or RuntimeError("no answer")

# Fields graded on an ordered scale, so several samples can be reduced to
# their median rather than to whichever answer happened to come back first.
VOTED = {"level": ["Low", "Medium", "High"]}
# The same idea for fields that are already numbers. These need it more than
# the labels do: three samples of the 0-100 theme fit move by a median of 7
# points and by as much as 27 on a contested game, so a single sample is a
# draw rather than a reading.
VOTED_NUM = ("fit", "style", "score")


def sample(prompt, model, online, samples):
    """One answer, or the per-field majority of several.

    Interaction labels flap: run the same prompt over the same 26 games three
    times and 6 to 11 of them come back different at least once, because the
    call is genuinely close for a lot of games. Scoring against the owner's
    own judgements, one sample lands at 22/26 and the median of three at
    23/26 — a point of accuracy, but mostly a lot less churn in a file that
    gets committed and published. It costs three times as much, so it is
    opt-in; the answers are cached per game either way, so a collection pays
    for it once.
    """
    answers = [ask(prompt, model, online=online) for _ in range(samples)]
    if len(answers) == 1:
        return answers[0]
    merged = {}
    for key in answers[0]:
        entries = [a[key] for a in answers if isinstance(a.get(key), dict)]
        if not entries:
            continue
        # The first answer supplies the prose; only the graded fields are
        # voted on, and a tie falls back to the first answer's value.
        out = dict(entries[0])
        for field in VOTED_NUM:
            for holder in ([out] if field in out else
                           [v for v in out.values() if isinstance(v, dict)
                            and field in v]):
                seen = []
                for e in entries:
                    box = e if field in e else next(
                        (v for v in e.values()
                         if isinstance(v, dict) and field in v), {})
                    val = box.get(field)
                    if isinstance(val, (int, float)):
                        seen.append(val)
                if seen:
                    holder[field] = int(round(sorted(seen)[len(seen) // 2]))
        for field, order in VOTED.items():
            for holder in ([out] if field in out else
                           [v for v in out.values() if isinstance(v, dict)
                            and field in v]):
                seen = []
                for e in entries:
                    box = e if field in e else next(
                        (v for v in e.values()
                         if isinstance(v, dict) and field in v), {})
                    val = box.get(field)
                    if val in order:
                        seen.append(order.index(val))
                if seen:
                    holder[field] = order[sorted(seen)[len(seen) // 2]]
        merged[key] = out
    return merged


def process(batch, model, describe=False, online=False, rescore=False,
            endings=False, sources=False, scores=False, interaction=False,
            theme=False, style=False, samples=1):
    # --rescore --online asks only for the scoring facts, but with the web
    # open: the rules of a game are written down somewhere, and a fact the
    # model half-remembers is exactly the case worth looking up.
    header = (THEME if theme
              else STYLE if style
              else (INTERACTION_WEB if online else "") + INTERACTION if interaction
              else SCORES if scores
              else SOURCES if sources
              else ENDINGS if endings
              else (RESCORE_WEB if online else "") + RESCORE.format(rule=FACTS_BRIEF)
              if rescore
              else ONLINE.format(rule=FACTS_BRIEF) if online
              else DESCRIBE if describe else None)
    answers = sample(prompt_for(batch, header), model, online, samples)
    written = []
    for g in batch:
        data = answers.get(str(g["id"])) or answers.get(g["id"])
        if not isinstance(data, dict):
            continue
        if online:
            data["source"] = "web"
        if theme or style:
            # Only the new axis is written; nothing else in the record moves.
            key = "theme" if theme else "style"
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            got = data.get(key)
            if got:
                existing.setdefault(key, {}).update(got)
            data = existing
        elif interaction:
            # Only the interaction facts are rewritten; the level itself is
            # computed from them at render time.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            got = data.get("interaction")
            if got:
                existing.setdefault("interaction", {}).update(got)
            data = existing
        elif scores:
            # Only the winning-score range is written; everything else stands.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            rng = data.get("score_range")
            sc = existing.setdefault("scoring", {})
            sc["score_range"] = rng if isinstance(rng, list) and len(rng) == 2 else None
            if data.get("note"):
                sc["score_note"] = data["note"]
            data = existing
        elif sources:
            # Only the list of scoring categories is re-asked; the winning
            # score, the endings and anything checked on the web stay put.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            got = data.get("sources")
            if got:
                existing.setdefault("scoring", {})["sources"] = got
            data = existing
        elif endings:
            # Only the endings are re-asked; every number in the entry — the
            # sources, the winning score, whatever was checked on the web —
            # stays exactly as it was.
            existing = json.loads((AI / f'{g["id"]}.json').read_text())
            ends = data.get("endings")
            if ends:
                existing.setdefault("scoring", {})["endings"] = ends
            data = existing
        elif rescore:
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
    ap.add_argument("--samples", type=int, default=1, metavar="N",
                    help="ask N times and keep the median of the graded "
                         "fields; steadier labels for N times the money")
    ap.add_argument("--describe", action="store_true",
                    help="second pass over low-confidence entries")
    ap.add_argument("--online", action="store_true",
                    help="look entries up on the web (slow, costs real money)")
    ap.add_argument("--only", metavar="IDS",
                    help="comma-separated game ids, for retrying the handful "
                         "a failed batch left behind")
    ap.add_argument("--theme", action="store_true",
                    help="re-ask only how tightly mechanics fit the theme")
    ap.add_argument("--style", action="store_true",
                    help="re-ask only where a game sits on euro-ameritrash")
    ap.add_argument("--interaction", action="store_true",
                    help="re-ask only how players affect each other")
    ap.add_argument("--scores", action="store_true",
                    help="re-ask only the typical winning-score range")
    ap.add_argument("--sources", action="store_true",
                    help="re-ask only which categories a game scores, "
                         "merging into the facts already there")
    ap.add_argument("--endings", action="store_true",
                    help="re-ask only how each game can end, and what settles "
                         "it, merging into the facts already there")
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
        if (a.endings or a.sources or a.scores or a.interaction
                or a.theme or a.style):
            if not cached.exists():
                continue
            try:
                facts = json.loads(cached.read_text()).get("scoring") or {}
            except Exception:  # noqa: BLE001
                facts = {}
            # A verified record may still be missing what settles each of
            # its endings; scoring.py keeps the verified endings and takes
            # only the decisions from this pass.
            if a.endings and facts.get("endings") and not a.force:
                continue
            if a.scores and "score_range" in facts and not a.force:
                continue
            if (a.theme or a.style) and not a.force:
                key = "theme" if a.theme else "style"
                field = "fit" if a.theme else "style"
                rec = json.loads(cached.read_text()).get(key) or {}
                if isinstance(rec.get(field), (int, float)):
                    continue
            if a.interaction and not a.force:
                ix = json.loads(cached.read_text()).get("interaction") or {}
                # "said" is what the current pass writes. Records from the
                # earlier schemes carry a level without it, and those are
                # exactly the ones worth re-asking, so the skip has to key on
                # the new field rather than on merely having a level.
                if ix.get("said"):
                    continue
            todo.append(g)
            continue
        if a.rescore:
            if not cached.exists():
                continue
            try:
                facts = (json.loads(cached.read_text()).get("scoring") or {})
            except Exception:  # noqa: BLE001
                facts = {}
            # Facts read off a rules page beat facts recalled from memory, so
            # an offline re-ask leaves them alone unless told otherwise.
            if facts.get("checked") and not (a.force or a.online):
                continue
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
                               a.online, a.rescore, a.endings,
                               a.sources, a.scores, a.interaction,
                               a.theme, a.style, a.samples): b
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
