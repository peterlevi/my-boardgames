# bgg-collection-data

A local cache of a BoardGameGeek collection plus small scripts to refresh and
query it — so questions like "what plays great at 4?" can be answered offline,
without hammering BGG.

Cached snapshot: **242 owned base games** (expansions excluded), fetched
2026-09-10.

## Layout

```
credentials.env          BGG username + API token (gitignored)
credentials.env.example  template
point-salads.txt         hand-maintained exclusion list (see below)
data/raw/                verbatim BGG XML — collection.xml + thing_*.xml
data/games.json          normalised, the thing every query reads
scripts/fetch.py         raw XML  <- BGG          (network; slow, be sparing)
scripts/build.py         games.json <- raw XML    (offline, instant)
scripts/query.py         table      <- games.json (offline, instant)
```

## Query it

```bash
python3 scripts/query.py --players 4                              # great/best at 4
python3 scripts/query.py --players 4 --exclude-file point-salads.txt --format md
python3 scripts/query.py --players 2 --max-weight 2.5 --max-time 45
python3 scripts/query.py --players 5 --min-approval 90 --format json
```

Definitions used throughout, all from BGG's `suggested_numplayers` poll:

- **Best at N** — N received more "Best" votes than any other player count.
- **Great at N** — at least `--min-best` percent (default 50) of voters at N
  called it the Best count. Catches games where the vote splits across counts
  but N is still strongly liked.
- **Approval at N** — (Best + Recommended) / all votes at N. A game can have
  99% approval and still not be *best* at N.

Games with fewer than `--min-votes` (default 10) poll votes at N are dropped —
below that the percentages are noise.

## Refresh from BGG

```bash
python3 scripts/fetch.py          # only fetches what is missing
python3 scripts/fetch.py --force  # refetch everything (~14 requests, ~2 min)
python3 scripts/build.py
```

## Notes on the BGG API (learned the hard way)

- **The XML API v2 now requires a bearer token.** Every endpoint returns
  `401` with `WWW-Authenticate: Bearer realm="xml api"` otherwise. The token
  goes in `credentials.env`.
- **Scraping the website instead does not work** — boardgamegeek.com sits
  behind a Cloudflare bot challenge that returns `403` to plain HTTP clients,
  and the challenge cannot complete under a filtering proxy. Use the API.
- **`/thing?id=` accepts at most 20 ids** per request; 50 returns `400`.
- **`/collection` returns `202` on a cold request** and queues the export —
  poll until it returns `200`. `fetch.py` handles this.
- **Most XML scalars are in a `value` attribute**, not element text:
  `<playingtime value="90"/>`, `<averageweight value="3.86"/>`. `findtext()`
  silently returns empty for these.
- **Use `curl`, not `urllib`** — under the Claude Code sandbox urllib raises
  `IncompleteRead` partway through these responses.
- Be sparing. `fetch.py` spaces requests 6s apart; don't remove that.

## point-salads.txt

Purely a taste filter, not BGG data — a list of games where points arrive from
many loosely-coupled sources. It is a judgment call and meant to be edited.
Pass it to any query with `--exclude-file point-salads.txt`.

## Unranked entries

A few rows show rank `—`. These are Big Box / anniversary editions that BGG
keeps as separate unranked entries (e.g. *Istanbul: Big Box*); the ranked
entry is the base game.
