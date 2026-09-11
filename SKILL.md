---
name: bgg-collection
description: Answer questions about the user's BoardGameGeek collection — which owned games suit a player count, filtered by complexity, length, interaction, play count, rank or point-salad-ness — and render an interactive HTML report of it. Use whenever the user asks what to play, what suits a group size, or anything about games they own.
---

# BGG collection

A cached copy of the user's owned games and expansions, with query and report
scripts. Everything except `fetch.py` is offline and instant.

**Location:** this repository (`~/hs/bgg-collection-data` locally)

## Answer questions with `query.py` — do not re-fetch

```bash
python3 scripts/query.py --players 4 --exclude-file point-salads.txt --format md
```

Flags: `--players N`, `--min-best PCT` (default 50), `--min-approval PCT`,
`--min-votes N` (default 10), `--min-weight` / `--max-weight`,
`--max-time MIN`, `--exclude-file FILE`, `--format txt|md|json`. Output sorts
by BGG rank ascending, unranked last.

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
a parse error there and silently disables everything. Run `scripts/thumbs.py`
once first if `data/thumbs/` is empty.

For anything the flags don't cover, read `data/games.json` directly — one
object per game with `name`, `rank`, `weight`, `average`, `year`, `plays`,
`minplayers`/`maxplayers`, `minplaytime`/`maxplaytime`, `mechanics`,
`categories`, `interaction`, `point_salad`, `is_expansion`, `expands`, and the
raw `poll` (`{"4": {"Best": n, "Recommended": n, "Not Recommended": n}}`).

## Terms

- **Best at N** — N got more Best votes than any other count.
- **Good at N** — Best at N, or ≥50% of voters at N called N best.
- **Approval at N** — (Best + Recommended) ÷ total votes at N.

Report Best and Approval separately; they say different things. A party game
can be 99% approved at 4 while being Best at 6.

## Say when a column is an opinion

`interaction`, `breadth` and `traits` are **derived locally, not BGG data** —
BGG exposes none of them. Whenever you present any of them, say so.

`breadth` is a four-level scale (Focused / Some / Broad / Salad) computed from
counted evidence in the mechanic and family tags; it names no games. `traits`
lists why, and is multi-selectable, so combinations like "broad scoring but a
contested market" are askable. Correct individual games in
`breadth-overrides.txt`, tune the model in `scripts/breadth.py` or
`scripts/interaction.py`, then re-run `build.py`.

## Refreshing (network — needs the user's OK)

`scripts/fetch.py` makes ~16 requests to BGG spaced 6s apart, then
`scripts/build.py` regenerates `games.json`. Only do this if the user asks or
the cache is clearly stale (check `data/raw/collection.xml` mtime). The API
needs a bearer token, already in the gitignored `credentials.env`.

Don't scrape boardgamegeek.com — Cloudflare returns 403 to non-browser clients.
See README.md for the rest of the API's quirks and for geekgroup.app as a
fallback source.
