# my-boardgames

An offline cache of a [BoardGameGeek](https://boardgamegeek.com) collection and
a single-file HTML report for answering the question you actually ask on a game
night: *what should we play, with this many people, in this much time?*

**→ [Browse the live report](https://peterlevi.github.io/my-boardgames/)**

Everything but the initial fetch runs offline, so day-to-day use costs no API
calls. The published page is rebuilt from the cached data on every push.

## What the report does

One self-contained HTML file holding the whole collection, filtered in the
browser:

- **Player count** with three rules — plays at N, *good* at N, or *best* at N,
  read from BGG's own `suggested_numplayers` poll
- **Expansions** folded in: an owned expansion can qualify its base game at a
  count the base game can't manage alone
- **Complexity**, **play time**, **BGG score**, **number of plays**, all as ranges
- **Point salad** — yes / no / doesn't matter
- **Level of interaction** — low / medium / high
- Name search, and every column sortable

Thumbnails are embedded in the file, so it works with no network and survives
being mailed or dropped into a chat client.

### Two columns are opinions

**Interaction** is not a BGG statistic. Their API has no such field, and
neither does geekgroup's — nothing authoritative exists to import. It is
derived in [`scripts/interaction.py`](scripts/interaction.py) from each game's
mechanics and categories: tags that mean players act *on* each other score
High, competition over a shared pool scores Medium, parallel play scores Low,
with a handful of documented overrides where BGG's tags mislead.

**Point salad** is a hand-maintained list in
[`point-salads.txt`](point-salads.txt).

Both are meant to be argued with. Edit either file, re-run `build.py`, and the
report follows.

## Quick start

```bash
git clone https://github.com/peterlevi/my-boardgames.git
cd my-boardgames
pip install -r requirements.txt

# The cached data is committed, so you can render immediately:
python3 scripts/build.py
python3 scripts/report.py -o reports/collection.html
open reports/collection.html
```

To point it at **your own** collection, see Configuration below.

## Configuration

Copy the template and fill it in:

```bash
cp credentials.env.example credentials.env   # already gitignored
```

```ini
BGG_USERNAME=your-bgg-username
BGG_TOKEN=your-bgg-api-token
```

BGG's XML API v2 requires a bearer token — every endpoint answers `401` with
`WWW-Authenticate: Bearer realm="xml api"` without one. Generate it from your
BGG account; see [the XML API
documentation](https://boardgamegeek.com/wiki/page/BGG_XML_API2). Environment
variables of the same names override the file, which is how CI would pass a
token if you ever automate the fetch.

Then pull your collection and build:

```bash
python3 scripts/fetch.py     # ~16 requests to BGG, spaced 6s apart
python3 scripts/thumbs.py    # one-time thumbnail cache
python3 scripts/build.py
python3 scripts/report.py -o reports/collection.html
```

## How it works

```
scripts/fetch.py    BGG XML API      ->  data/raw/*.xml       (network, slow, rare)
scripts/thumbs.py   BGG image CDN    ->  data/thumbs/*.jpg    (network, once)
scripts/build.py    data/raw         ->  data/games.json      (offline, instant)
scripts/report.py   data/games.json  ->  a single HTML file   (offline, instant)
scripts/query.py    data/games.json  ->  a terminal table     (offline, instant)
```

Only the first two touch the network. `data/raw/` and `data/thumbs/` are
committed, which is what lets CI rebuild the page without credentials.

### Terminal queries

```bash
python3 scripts/query.py --players 4 --exclude-file point-salads.txt
python3 scripts/query.py --players 2 --max-weight 2.5 --max-time 45
python3 scripts/query.py --players 5 --min-approval 90 --format json
```

### Report options

`scripts/report.py` takes the same filters; they set which state the page
*opens* in, not what it contains.

```bash
python3 scripts/report.py --players 5 --mode best -o reports/best-at-5.html
python3 scripts/report.py --link-thumbs -o reports/small.html   # ~130 KB, needs internet
```

## Hosting

The live page is built and published by
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) on every push to
`main`, using GitHub Pages' artifact deployment — there is no `gh-pages`
branch, and no build output is committed.

The build is offline and needs no secrets, which is the whole reason this is
safe to run on every push. Refreshing from BGG stays a deliberate, local step.

Repository **Settings → Pages → Source** must be set to **GitHub Actions**.

## Definitions

From BGG's `suggested_numplayers` poll:

- **Best at N** — N received more "Best" votes than any other player count.
- **Good at N** — Best at N, or ≥50% of voters at N called N the best count.
- **Approval at N** — (Best + Recommended) ÷ all votes at N. A game can be 99%
  approved at N and still be *best* at a different count.

Counts with fewer than the minimum poll votes (default 10) are ignored; below
that the percentages are noise.

## Notes on the BGG API

Collected the hard way, in case they save someone else the trouble:

- **The XML API v2 requires a bearer token** — everything is `401` without one.
- **Scraping the website instead does not work.** boardgamegeek.com sits behind
  a Cloudflare bot challenge that returns `403` to plain HTTP clients.
- **`/thing?id=` accepts at most 20 ids** per request; 50 returns `400`.
- **`/collection` returns `202` on a cold request** and queues the export —
  poll until it returns `200`. `fetch.py` handles this.
- **Expansions are a separate subtype.** The base query passes
  `excludesubtype=boardgameexpansion`; expansions need their own
  `subtype=boardgameexpansion` query.
- **Play counts ride along** with the collection export (`stats=1`) — no extra
  requests needed.
- **Most XML scalars live in a `value` attribute**, not element text:
  `<playingtime value="90"/>`. `findtext()` silently returns empty for these.
- Be sparing. `fetch.py` spaces requests 6 seconds apart; please leave that in.

[geekgroup.app](https://geekgroup.app) exposes a JSON API
(`api.geekgroup.app/api/users/collection.json`, POST, paginated) that mirrors a
public BGG collection with rank, weight, polls, language dependency and
estimated worth. It was checked as a second source and adds nothing this cache
doesn't already have — including no interaction data. Useful as a fallback if
BGG's API is down.

## Browser support

The report's script stays within ES2019 and the page is rendered server-side,
so the table is complete and readable even where scripts don't run at all —
Slack's mobile file preview, for instance. Filtering and sorting need
JavaScript; a `<noscript>` note says so.

## Licence

MIT for the code. The collection data under `data/` is BoardGameGeek's,
retrieved through their API and subject to
[their terms of use](https://boardgamegeek.com/xmlapi/termsofuse).
