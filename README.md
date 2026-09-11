# bgg-collection-data

A local cache of a BoardGameGeek collection, plus scripts to refresh it and to
render it as an interactive HTML report. Everything except `fetch.py` runs
offline, so day-to-day questions cost zero API calls.

Cached snapshot: **242 owned games + 23 owned expansions**, fetched 2026-09-10.

## Layout

```
credentials.env          BGG username + API token (gitignored)
credentials.env.example  template
point-salads.txt         hand-maintained "point salad" list
data/raw/                verbatim BGG XML — collection, expansions, thing_*, exp_*
data/games.json          normalised; every script reads this
data/thumbs/             downscaled thumbnails, inlined into reports
reports/                 generated HTML (gitignored)
scripts/fetch.py         raw XML   <- BGG          (network; slow, be sparing)
scripts/build.py         games.json <- raw XML     (offline, instant)
scripts/query.py         terminal table <- games.json
scripts/report.py        HTML report    <- games.json + data/thumbs
scripts/thumbs.py        thumbnail cache <- BGG image CDN (network, once)
scripts/report_template.html   the report's markup, CSS and browser-side filtering
scripts/interaction.py   the derived "level of interaction" classifier
scripts/common.py        credentials, paths, shared filter logic
```

## The HTML report

```bash
python3 scripts/report.py -o reports/collection.html
python3 scripts/report.py --players 5 --mode best -o reports/best-at-5.html
```

The page embeds the **whole** collection and filters in the browser, so one
file answers any question. The CLI flags only set which filters it opens with.

Every row is also **rendered server-side** as real markup, and the controls
carry their selected state in the HTML. So when the script cannot run — Slack's
mobile file preview does not execute it — the table is still complete,
readable, and in rank order, showing whatever the opening filters describe;
only filtering and sorting are lost, and a `<noscript>` note says so. For the
same reason the page script stays within ES2019: an ES2021 `||=` was a parse
error in that webview, which silently killed the entire script.
Available in the page: name search, player count, the Best/Good rule, point
salad (yes/no/doesn't matter), interaction level, complexity range, time range,
play-count range, minimum poll votes, and expansion handling. Every column
sorts.

### Expansion handling

Three modes, because an expansion can change which counts a game plays well at:

- **Hide, but count for base game** (default) — expansion rows are hidden, but
  an owned expansion's player-count poll can qualify its base game at a count
  the base game alone doesn't support. An expansion only speaks when the base
  game does *not* already qualify, so a 13-vote expansion poll can never
  displace a 1300-vote base one. Rows qualified this way are badged `+EXP`.
- **Show as their own rows** — expansions listed alongside games.
- **Ignore completely** — base games only.

Thumbnails are inlined as data URIs from `data/thumbs/` so the file is fully
self-contained (~1.5 MB) — external images are blocked in Slack and elsewhere.
Run `python3 scripts/thumbs.py` once to populate that cache; `--link-thumbs`
builds the ~130 KB hotlinking version instead.

## Terminal queries

```bash
python3 scripts/query.py --players 4 --exclude-file point-salads.txt
python3 scripts/query.py --players 2 --max-weight 2.5 --max-time 45
python3 scripts/query.py --players 5 --min-approval 90 --format json
```

## Definitions

From BGG's `suggested_numplayers` poll:

- **Best at N** — N received more "Best" votes than any other player count.
- **Good at N** — Best at N, or ≥50% of voters at N called N the best count.
- **Approval at N** — (Best + Recommended) ÷ all votes at N. A game can have
  99% approval at N and still be *best* at some other count.

Counts with fewer than the minimum poll votes (default 10) are ignored; below
that the percentages are noise.

Two columns are **not** BGG data and are opinions:

- **Interaction** (Low / Medium / High) — derived by `scripts/interaction.py`
  from each game's mechanics and categories. BGG's API has no interaction
  field and neither does geekgroup's, so there is nothing authoritative to
  import. The rule and its known overrides are documented in that file.
- **Point salad** — the hand-maintained `point-salads.txt`. Edit and re-run
  `build.py`.

## Refresh from BGG

```bash
python3 scripts/fetch.py          # only fetches what is missing
python3 scripts/fetch.py --force  # refetch everything (~16 requests, ~2.5 min)
python3 scripts/build.py
```

Play counts come free with the collection export (`stats=1`), so they need no
extra requests.

## Notes on the BGG API (learned the hard way)

- **The XML API v2 requires a bearer token.** Everything returns `401` with
  `WWW-Authenticate: Bearer realm="xml api"` otherwise. Token lives in
  `credentials.env`.
- **Scraping the website is not an option** — boardgamegeek.com is behind a
  Cloudflare bot challenge that returns `403` to plain HTTP clients and cannot
  complete under a filtering proxy.
- **`/thing?id=` accepts at most 20 ids** per request; 50 returns `400`.
- **`/collection` returns `202` on a cold request** and queues the export —
  poll until `200`. `fetch.py` handles this.
- **Expansions are a separate subtype.** The base collection query passes
  `excludesubtype=boardgameexpansion`; expansions need their own
  `subtype=boardgameexpansion` query.
- **Most XML scalars live in a `value` attribute**, not element text:
  `<playingtime value="90"/>`. `findtext()` silently returns empty for these.
- **Use `curl`, not `urllib`** — under the Claude Code sandbox urllib raises
  `IncompleteRead` partway through these responses.
- Be sparing. `fetch.py` spaces requests 6s apart; don't remove that.

### geekgroup.app

`https://api.geekgroup.app/api/users/collection.json` (POST, paginated, no auth
needed for a public collection) mirrors a BGG collection with rank, weight,
player-count poll, language dependency, age and estimated worth. It was checked
as a second source and adds nothing this cache doesn't already have — in
particular it has **no** interaction data either. Useful as a fallback if BGG's
API is unavailable.

## Unranked entries

Some rows show rank `—`. These are Big Box / anniversary editions that BGG
keeps as separate unranked entries (e.g. *Istanbul: Big Box*); the ranked entry
is the base game.
