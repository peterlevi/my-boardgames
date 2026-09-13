# What is unfinished

## Two new axes, measured but not run

`enrich.py --theme` (how tightly the mechanics fit the theme) and
`--style` (euro against ameritrash) both work and are validated on a 20-game
probe. What is left is a full run, a reference file of the owner's calls, and
the columns. Detail, numbers and costs are in
`PLAN-thematic-ameritrash.md`. Roughly **$19** for both at `--samples 3`
across 242 games.

Worth knowing before starting: the euro/ameritrash axis has free ground truth
already cached. BGG sorts its own games into sections, and those come through
`build.py` as `types` on every game — this collection has 203 Strategy, 46
Family, 15 Party, 11 Thematic, 9 War Game and 8 Abstract. No reference file
is needed to tell whether that axis is behaving.

## A reference file for thematic fit

`tests/interaction_calls.txt` is the model to copy. Seed it with the five
calls already recorded in the plan, and settle the one open disagreement
(Brass: Birmingham) first.

## Known holdout in the salad rules

`check_scoring.py` reports 39 of 40. Carcassonne Big Box is the failure: the
rules make it a full point salad, the owner says at most a touch. Every
scorepad line comes out of placing one tile, which the rules should probably
weigh more heavily than they do. Left failing on purpose rather than
special-cased.

## Render fewer rows if a collection is ever large

At around 2,000 games the page is still fine; at 10,000 the browser spends
most of a second laying out the table on every render. Capping the rendered
rows at a few hundred with a "show the rest" control is the fix, and nothing
else needs optimising. Not worth doing for a collection this size — the
numbers are in `LEARNINGS.md` if it ever is.

## Interaction levels are judged, and could carry their evidence

The pass already returns the phrases players use (`said`) alongside the
level, and the report does not show them. Surfacing that in the expanded row
would make the most opinion-shaped column in the table auditable by the
reader. Small change; nobody has asked for it yet.
