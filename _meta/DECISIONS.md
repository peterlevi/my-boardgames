# Decisions, with the reasoning

Reverted decisions are kept. The reason a thing was abandoned is worth more
than the fact that it is absent.

## D-1 — One self-contained HTML file

The report is a single file with thumbnails embedded, no build step for the
reader and no network calls when it opens. It can be mailed, opened from a
USB stick, or served from Pages unchanged. The cost is file size (~3MB for
265 games); the benefit is that it still works in five years.

## D-2 — Facts from the model, verdicts from code

For anything that can be derived, the model reports checkable facts and the
rules live in `scoring.py`. Asked for verdicts directly it guesses plausibly
and wrongly, and there is nothing to argue with. Rules can be read, tested
and corrected; a vibe cannot. `tests/expectations.txt` pins them.

## D-3 — Interaction is judged, not computed (after trying the opposite)

Weighing interaction from facts — a shared board, blocking on it, acting on
an opponent, a common market, negotiation — was implemented and reverted. It
has no way to see an auction: Ra, High Society and Medici came out *Low*,
where bidding against each other is the entire game. The failure is recorded
at the top of `scoring.py` so it is not retried blind.

What works instead is a prompt that demands **evidence before the verdict**:
what do players actually call this game, then the mechanism, then the level.
Measured at 22/26 against the owner's own calls, where asking for a level
directly, asking what the community says, and searching the web with
citations all scored 21/26 — the last at ten times the cost.

## D-4 — Point salad is a number; the words are bands

`salad_score()` returns 0-100 and `salad()` cuts bands from it. Two
consequences: how many bands the report shows is presentation only, and the
axis has no sampling noise because it is arithmetic over facts. Moving from
stepped labels to a ramped number changed 21 of 242 verdicts, all downward,
and fixed plain errors — the old rule compounded a full level per condition
and called Lost Cities and Azul full point salads.

## D-5 — The acceptance tests are the owner's own judgements

`tests/expectations.txt` and `tests/interaction_calls.txt` record what a
person who has played the games says. They are the only defence against a
rule that is elegant and wrong. When a rule and a call disagree, either the
rule improves or the disagreement is documented as a known holdout — the
game is never special-cased by name. There is one standing holdout
(Carcassonne Big Box on the salad axis) and it is honest.

## D-6 — Private data is excluded by architecture, not by discipline

Price paid and the rest are merged at render time from a gitignored CSV, so
the committed data cannot carry them even by accident and a build without the
file just shows blanks. Chosen over "remember not to publish the field".

## D-7 — The URL carries the view; storage carries the habit

Filters, sort and the expanded game live in the URL hash, so a view is
shareable down to a single game. `localStorage` is the fallback for when the
URL says nothing, and column choices live there alone because they are a
preference, not a view worth sending. Expanding a game pushes a history
entry; a filter change replaces one — a history step per keystroke would make
the back button useless.

## D-8 — Search matches words, not the whole box

Every word must land somewhere in the row's metadata, but they need not be
adjacent or in order, and accents are folded on both sides. Matching the
whole box as one string meant "board dice" found nothing while "Board&Dice"
found seven games. BGG's alternate titles are searchable but never displayed.

## D-9 — Batch the model calls; cache and commit the answers

The agent's startup dominates its thinking, so eight games per call costs
roughly what one does. Every answer is cached per game and committed, so a
resync pays only for genuinely new games and anyone cloning the repo pays
nothing. Measured at about $0.013 a game.

## D-10 — The screenshot commit in CI must tolerate a race

The workflow commits refreshed screenshots and pushes them. Any commit
landing on the branch in between makes a bare push fail on a race that has
nothing to do with screenshots, turning a good build red. It retries,
rebasing onto whatever arrived; the commit only ever touches `docs/*.png`, so
it cannot conflict with source.
