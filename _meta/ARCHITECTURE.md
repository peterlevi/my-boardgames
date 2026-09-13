# How the pipeline fits together

## The order, and the step everyone forgets

```
fetch.py     BGG XML API      -> data/raw/**            (network, token)
thumbs.py    image CDN        -> data/thumbs/*.jpg      (network)
gallery.py   geekdo           -> data/gallery/*.json    (network)
build.py     data/raw/**      -> data/games.json        (offline)
enrich.py    `claude` CLI     -> data/ai/<id>.json      (optional, costs money)
bggids.py    BGG search       -> data/bgg_ids.json      (network, tiny)
build.py     again            -> data/games.json        (offline)
report.py    data/games.json  -> one HTML file          (offline)
```

`sync.py` runs all of that in order and is the right way to do a full refresh.

**The second `build.py` is not optional, and skipping it wastes an hour.**
`report.py` renders from the `ai` payload that `build.py` copies *into*
`data/games.json`; it never reads `data/ai/` directly. The checking scripts
do read `data/ai/` directly. So an `enrich.py` run that is not followed by a
`build.py` run changes nothing on screen while the checks happily report new
numbers, and the two disagree with no error anywhere. `report.py` prints a
warning when it notices `data/ai/` is newer, but only `sync.py` gets the
order right for free.

## What each script owns

| script | owns |
|---|---|
| `fetch.py` | every network call to the BGG XML API, and the rate limiting |
| `build.py` | normalising cached XML into one `data/games.json`, and merging `data/ai/` into it |
| `enrich.py` | every prompt sent to the model, and the cache of answers |
| `scoring.py` | win condition, point salad, winning-score range — computed from facts, never asked for |
| `interaction.py` | the fallback interaction rule used when the opinion database is missing |
| `traits.py` | named groupings of BGG's granular mechanic vocabulary |
| `report.py` | the server-rendered rows, and everything that must exist without JavaScript |
| `report_template.html` | the page's markup, styles and browser-side code |
| `screenshot.py` | a PNG of the built report, for the README; CI renders it into the published site, never into the repository |
| `common.py` | paths, credentials, filter logic shared between `query.py` and `report.py` |
| `query.py` | the terminal answer to "what should we play" |
| `check_scoring.py`, `check_interaction.py` | the acceptance tests |

## The pattern that makes the derived columns trustworthy

Asking a model for a *label* gets you a vibe. Asking it for *facts* and
applying rules in code gets you something you can argue with.

**Win condition** and **point salad** follow this: `enrich.py` asks what a
winning score looks like, how many separate subsystems feed it, how many
categories the rules total, whether points are tallied as you go or at the
end, and how the game ends. `scoring.py` turns those into labels by rules you
can read. Asked for the labels directly, the same model filed Food Chain
Magnate — whose only currency is money — as a broad point salad.

Point salad is computed as a **0-100 number first**, and the words are bands
cut from it (`SALAD_BANDS`). There is no sampling noise in it at all, because
it is arithmetic over facts. How many bands the report shows is therefore a
presentation choice, not a property of the data.

**Interaction** does not work that way, and the failed attempt is documented
in `scoring.py` — weighing a shared board, blocking, acting on an opponent, a
common market and negotiation produced *Low* for Ra, High Society and Medici,
because an auction has no board and no blocking. It is a judgement, and the
prompt that works asks for the community's own words *before* the verdict.

## The report is progressive, not an app

Rows are server-rendered with every cell present, so the page is a readable
table with JavaScript switched off. The browser-side script filters, sorts,
expands and remembers; it is ES2019, no build step, no dependencies, and it
all lives in `report_template.html`.

Three pieces of state, in three places, deliberately:

- **Columns and their order** — `localStorage`, applied by a small script in
  `<head>` *before first paint*, so the table paints once in its final shape.
  The head script and the page script must use the same storage key; they
  drifted apart once and the symptom was a visible reflow on every load.
- **Filters, sort, and the expanded game** — the URL hash, so a view is
  shareable, and `localStorage` as the fallback when the URL carries nothing.
  Expanding a game pushes a history entry; changing a filter replaces one.
- **Everything else** — recomputed per render.
