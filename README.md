# my-boardgames

An offline cache of a [BoardGameGeek](https://boardgamegeek.com) collection and
a single-file HTML report for answering the question you actually ask on a game
night: *what should we play, with this many people, in this much time?*

**→ [Browse the live report](https://peterlevi.github.io/my-boardgames/)**

[![The report](docs/screenshot.png)](https://peterlevi.github.io/my-boardgames/)

Everything but the fetch runs offline, so day-to-day use costs no API calls.
The published page and the screenshot above are both rebuilt from the cached
data on every push.

## What the report does

One self-contained HTML file holding the whole collection, filtered in the
browser:

- **Player count** with three rules — plays at N, *good* at N, or *best* at N,
  read from BGG's own `suggested_numplayers` poll
- **Expansions** folded in: an owned expansion can qualify its base game at a
  count the base game can't manage alone
- **BGG score** and **your own rating** side by side, as BGG's rating hexagons
- **Complexity**, **play time**, **number of plays**, all as ranges
- **Scoring breadth** — Focused / Some / Broad / Salad, plus a multi-select of
  the underlying scoring traits (end-game bonuses, contested market, auction, …)
- **Level of interaction** — low / medium / high
- Name search, and every column sortable

Thumbnails are embedded in the file, so it works with no network and survives
being mailed or dropped into a chat client.

### A local opinion database (optional)

`scripts/enrich.py` builds `data/ai/<id>.json` — one grounded summary per game
— using the `claude` CLI if it is on PATH, and skipping cleanly if it is not.
That is where **Wins by**, **Breadth**, the interaction *kind*, and the "what
people say" panel come from.

```bash
python3 scripts/sync.py              # runs it as part of the pipeline
python3 scripts/enrich.py            # or on its own
python3 scripts/enrich.py --force    # redo everything
python3 scripts/sync.py --no-ai      # skip it deliberately
```

Three passes, in increasing order of cost:

| pass | what it asks | cost per game |
|---|---|---|
| default | what the model already knows, grounded in the BGG data | ~$0.002 |
| `--describe` | how it plays, from the BGG text only — no reception | ~$0.002 |
| `--online` | searches the web and cites its sources | ~$0.07 |

`--online` exists because training data is simply *absent* for recent games,
not vague. Fifteen games here came back "low confidence"; looking them up
found, for instance, that Daitoshi is Devir's 2024 title by Dani García, part
of the Kemushi Saga — and returned sourced praise and criticism. All fifteen
now have real panels, headed "looked up on the web" and listing the pages used.

Batch size is what makes that affordable. One game per call measured at
**$0.60**, because the agent loop's fixed overhead dominates a single lookup;
five games in one call measured at **$0.338, or $0.068 each** — nearly ten
times cheaper. The whole collection online would be about $16 rather than
$145.

**Without it the report still works.** No `claude` on PATH and the step says
so and exits 0; the rest of the pipeline is unaffected. Interaction falls back
to the level derived from BGG's mechanics, the detail panel omits the opinion
block rather than showing empty fields, images fall back to BGG's single box
shot, and "How to play" falls back to a YouTube search. Verified by rendering
a copy of the collection with `data/ai` and `data/gallery` absent and `claude`
removed from PATH. A half-finished run is fine too: the cache is per game, so
some rows simply have more than others.

Three things make it trustworthy enough to put in a table:

- **Grounded, not recalled.** Every prompt carries the cached BGG description,
  mechanics, categories, weight and poll, and asks the model to reconcile what
  it knows against what is in front of it. That is what makes it work for
  games published after the model's training cutoff.
- **It is allowed to not know.** Each entry carries a confidence. A
  low-confidence game keeps its structural fields and its opinion fields are
  dropped rather than shown, so the report never presents a guess as a
  finding. On this collection: 200 high, 35 medium, 7 low.
- **Cached and committed.** Keyed by a fingerprint of the inputs plus a schema
  version, so a resync only pays for genuinely new games — and anyone cloning
  the repo gets the database without running it or needing the CLI at all.

Batching matters: one game per `claude` call took about 100 minutes for 242
games, because agent startup dominates. Eight per call takes about four
minutes.

### Two columns are opinions

**Interaction** is not a BGG statistic. Their API has no such field, and
neither does geekgroup's — nothing authoritative exists to import. It is
derived in [`scripts/interaction.py`](scripts/interaction.py) from each game's
mechanics and categories: tags that mean players act *on* each other score
High, competition over a shared pool scores Medium, parallel play scores Low,
with a handful of documented overrides where BGG's tags mislead.

**Scoring breadth** — how widely a game spreads its points, from *Focused*
(one contested currency decides it) to *Salad* (points come from everywhere) —
is derived in [`scripts/breadth.py`](scripts/breadth.py). It names no games:
the model counts *kinds of evidence* rather than weighting individual
mechanics, because a weighted table invites quietly encoding opinions and a
list of named games is a lookup, not a model.

It rests on a measured finding. Comparing broad-scoring games against focused
ones, the sharpest separator was how many **shared-pool** mechanics a game has
— an auction, a market, a stock track (focused games averaged 1.43, broad ones
0.19). Second was solo-play support (0.62 vs 0.07): a game that works alone is
one where your score comes from your own engine rather than from beating
anybody. Two plausible-sounding signals turned out worthless and are
deliberately absent — the raw count of mechanics (gap 0.03) and BGG weight
(0.17).

Against a set of reference games it agrees on 21 of 23. The two it misses,
left uncorrected so the model stays honest, are noted in
[`breadth-overrides.txt`](breadth-overrides.txt) — which ships empty.

The same mechanics also yield **scoring traits**, exposed as a multi-select, so
you can ask for combinations a single flag could never express: *broad scoring,
but still a contested market*.

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
scripts/sync.py      run the whole pipeline below, in order
scripts/fetch.py     BGG XML API      ->  data/raw/            (network)
scripts/thumbs.py    BGG image CDN    ->  data/thumbs/*.jpg    (network)
scripts/build.py     data/raw         ->  data/games.json      (offline, instant)
scripts/report.py    data/games.json  ->  a single HTML file   (offline, instant)
scripts/query.py     data/games.json  ->  a terminal table     (offline, instant)
scripts/screenshot.py  the report     ->  docs/screenshot.png  (offline)
```

Only `fetch.py` and `thumbs.py` touch the network. `data/raw/` and
`data/thumbs/` are committed, which is what lets CI rebuild the page without
credentials.

The cache is keyed one file per game (`data/raw/things/<id>.xml`), so a resync
only fetches games you did not already have. Your play counts and your own
ratings ride along with the collection export at no extra cost.

### Keeping it in sync

```bash
python3 scripts/sync.py            # the regular resync
python3 scripts/sync.py --full     # also refetch every game's details
python3 scripts/sync.py --no-fetch # rebuild from the cache, no network at all
```

`sync.py` runs fetch → thumbs → build → report. A routine resync costs three
BGG requests when nothing has changed — the two collection exports plus a
poll — and one more per twenty new games. Run it whenever you have logged
plays, changed ratings, or bought something, then commit `data/` and push;
the Pages workflow republishes the site.

To automate it, `.github/workflows/resync.yml` runs the same thing weekly. It
is **opt-in and dormant** until you add `BGG_USERNAME` and `BGG_TOKEN` as
repository secrets (Settings → Secrets and variables → Actions); without them
the job exits cleanly instead of failing. It is the only workflow that talks
to BGG, and so the only one that needs credentials.

### Terminal queries

```bash
python3 scripts/query.py --players 4 --breadth upto-some
python3 scripts/query.py --players 0 --breadth broad --trait "Contested market"
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
branch, and the report itself is never committed.

The same workflow re-renders `docs/screenshot.png` and commits it when it has
changed, so the image at the top of this file always matches the current
report. That commit is made with `GITHUB_TOKEN`, whose pushes deliberately do
not trigger further workflow runs, so it cannot loop.

The build is offline and needs no secrets, which is the whole reason it is safe
to run on every push.

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

## Requirements

Python 3.9 or newer, and [Pillow](https://pillow.readthedocs.io) for the
thumbnail cache (`pip install -r requirements.txt`). Nothing else is required
to fetch, build or render — everything else is the standard library plus
`curl`. Screenshots additionally want Playwright's Chromium, and fall back to
any local Chrome installation.

## Browser support

The report's script stays within ES2019 and the page is rendered server-side,
so the table is complete and readable even where scripts don't run at all —
Slack's mobile file preview, for instance. Filtering and sorting need
JavaScript; a `<noscript>` note says so.

## Licence

MIT for the code. The collection data under `data/` is BoardGameGeek's,
retrieved through their API and subject to
[their terms of use](https://boardgamegeek.com/xmlapi/termsofuse).
