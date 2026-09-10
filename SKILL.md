---
name: bgg-collection
description: Answer questions about the user's BoardGameGeek collection — which owned games play best at N players, filtered by weight, length, rank or approval. Use whenever the user asks what to play, what suits a player count, or anything about games they own.
---

# BGG collection

A cached copy of the user's owned BGG games with a query script. Everything
except `fetch.py` is offline and instant.

**Location:** `~/hs/bgg-collection-data`

## Answer questions with `query.py` — do not re-fetch

```bash
cd ~/hs/bgg-collection-data
python3 scripts/query.py --players 4 --exclude-file point-salads.txt --format md
```

Flags: `--players N`, `--min-best PCT` (default 50), `--min-approval PCT`,
`--min-votes N` (default 10), `--min-weight` / `--max-weight`,
`--max-time MIN`, `--exclude-file FILE`, `--format txt|md|json`.

Output is sorted by BGG rank ascending, unranked entries last.

For anything the flags don't cover, read `data/games.json` directly — one
object per game with `name`, `rank`, `weight`, `average`, `year`,
`minplayers`/`maxplayers`, `minplaytime`/`maxplaytime`, and the raw `poll`
(`{"4": {"Best": n, "Recommended": n, "Not Recommended": n}, ...}`).

## Terms

- **Best at N** — N got more Best votes than any other count.
- **Great at N** — ≥ `--min-best`% of voters at N called N the Best count.
- **Approval at N** — (Best + Recommended) / total votes at N.

Report Best and Approval separately; they say different things. A party game
can be 99% approved at 4 while being Best at 6.

## Refreshing (network — needs the user's OK)

`scripts/fetch.py` makes ~14 requests to BGG spaced 6s apart, then
`scripts/build.py` regenerates `games.json`. Only do this if the user asks or
the cache is clearly stale (check `data/raw/collection.xml` mtime). The API
needs a bearer token, already in the gitignored `credentials.env`.

Don't scrape boardgamegeek.com — Cloudflare returns 403 to non-browser
clients. See README.md for the rest of the API's quirks.

## Taste filters

`point-salads.txt` lists games excluded when the user asks to skip point
salads. It's a judgment list, not BGG data — if the user disagrees with an
entry, edit the file.
