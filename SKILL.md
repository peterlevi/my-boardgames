---
name: bgg-collection
description: Answer questions about the user's BoardGameGeek collection — which owned games suit a player count, filtered by complexity, length, interaction, play count, rank or point-salad-ness — and render an interactive HTML report of it. Use whenever the user asks what to play, what suits a group size, or anything about games they own.
---

# BGG collection

A cached copy of the user's owned games and expansions, with query and report
scripts. Everything except `fetch.py` is offline and instant.

**Location:** this repository. Every path below is relative to its root, and
the scripts resolve their own paths, so run them from wherever the checkout
happens to be.

## Answer questions with `query.py` — do not re-fetch

```bash
python3 scripts/query.py --players 4 --format md
```

Flags: `--players N` (0 = any), `--min-best PCT` (default 50),
`--min-approval PCT`, `--min-votes N` (default 10), `--min-weight` /
`--max-weight`, `--max-time MIN`, `--tag NAME` (repeatable — any BGG mechanic
or category), `--expansions drop|show`, `--format txt|md|json`. Output sorts by
BGG rank ascending, unranked last.

## Build the interactive report with `report.py`

```bash
python3 scripts/report.py -o reports/collection.html
```

One self-contained HTML file containing the whole collection, filtered in the
browser: search, player count, Best/Good rule, point salad, interaction,
complexity, time, plays, and expansion handling. Prefer this when the user
wants to explore rather than get one answer.

Rows are rendered server-side and thumbnails are inlined, so the file still
reads correctly where scripts or external images are blocked (Slack's mobile
preview does both). Keep the page script at ES2019 or older — newer syntax is
a parse error there and silently disables everything, and `report.py` refuses
to write unbalanced markup, so a stray tag fails the build rather than
rendering wrong.

Without a BGG token, drop a collection CSV export at `data/collection.csv`:
`build.py` falls back to it (no mechanics, poll percentages or images, but
ranks, ratings, weights, play counts and BGG's best/recommended player counts
all survive) and `sync.py` skips every network step. With a token, the same
file is still the only source of **price paid** and **acquisition date** —
read by `report.py` at render time, never folded into `data/games.json`, so
nothing private is committed or published.

`scripts/sync.py` runs the whole pipeline: fetch → plays → thumbs → gallery →
build → enrich → bggids → build → report. `plays.py` caches the play log
(`data/plays.json`), which is where "last played" comes from — the collection
export carries how many times you have played a game but not when. Everything except `fetch.py`, `thumbs.py`,
`gallery.py`, `enrich.py` and `bggids.py` is offline, and `enrich.py` skips
itself cleanly when the `claude` CLI is missing. `bggids.py` resolves the
similar-game names enrich.py produces into BGG ids (`data/bgg_ids.json`) so
those pills link at the game; unresolved names fall back to a BGG search.

For anything the flags don't cover, read `data/games.json` directly — one
object per game with `name`, `rank`, `weight`, `average`, `year`, `plays`,
`my_rating`, `last_played`, `minplayers`/`maxplayers`,
`minplaytime`/`maxplaytime`, `mechanics`, `categories`, `families`,
`designers`, `publishers`, `types`, `interaction`, `is_expansion`, `expands`, the raw `poll`
(`{"4": {"Best": n, "Recommended": n, "Not Recommended": n}}`), and `ai` — the
opinion entry, whose `scoring` block holds the facts the labels are computed
from.

**Win condition and point salad are not stored; they are computed.** Call
`scoring.wins(facts)` and `scoring.salad(facts)` on `game["ai"]["scoring"]`
rather than looking for a field, and `scoring.score_text(facts)` for the
winning-score range. `python3 scripts/check_scoring.py` says whether those
rules still agree with the judgements in `tests/expectations.txt`; run it after
touching either.

## Terms

- **Best at N** — N got more Best votes than any other count.
- **Good at N** — Best at N, or ≥50% of voters at N called N best.
- **Approval at N** — (Best + Recommended) ÷ total votes at N.

Report Best and Approval separately; they say different things. A party game
can be 99% approved at 4 while being Best at 6.

## Say when a column is an opinion

`interaction`, the scoring facts behind **Win condition** and **Point
salad**, the opinion text and
`traits` are **derived locally, not BGG data** — BGG exposes none of them.
Whenever you present any of them, say so.

Most come from `data/ai/`, the opinion database built by `scripts/enrich.py`
using the `claude` CLI. Each entry carries a `confidence`, and `source`:
absent means the model answered from what it knows, `"description"` means it
only read the BGG text, `"web"` means it searched and the entry cites its
sources. Interaction falls back to a tag rule in `scripts/interaction.py` when
the database is absent. `traits` are groupings of mechanics from
`scripts/traits.py` — "has at least one of these" — not judgments.

Tune those files or re-run `scripts/enrich.py --force`, then `build.py`.
`--rescore` re-asks only the scoring facts and merges them into the existing
entries, for when the classification rule changed rather than the game;
`--sources`, `--endings` and `--scores` each re-ask one part of them. Add
`--online` to any of those and the answer has to cite the page it came from,
which is what fixes a fact the model half-remembers.

## Refreshing (network — needs the user's OK)

`scripts/fetch.py` makes ~16 requests to BGG spaced 6s apart, then
`scripts/build.py` regenerates `games.json`. Only do this if the user asks or
the cache is clearly stale (check `data/raw/collection.xml` mtime). The API
needs a bearer token, already in the gitignored `credentials.env`.

Don't scrape boardgamegeek.com — Cloudflare returns 403 to non-browser clients.
See README.md for the rest of the API's quirks and for geekgroup.app as a
fallback source.
