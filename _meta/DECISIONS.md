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

## D-10 — Generated screenshots are published, never committed

The README's screenshots are rendered by CI into the published site and
linked absolutely, rather than committed to the repository.

They were committed at first, by a step inside the build that pushed them
back to the branch. Two costs followed. Any commit landing on the branch
between the job's checkout and that push made it fail on a race that had
nothing to do with screenshots, turning good builds red; a retry that rebased
fixed that, but only by working around the design. And because the images are
regenerated on every push, the repository accumulated a stream of
half-megabyte binaries that nothing ever reads back — most of its growth, for
files that are pure output.

Publishing them beside the report removes the write permission, the bot
commit and the race together. The cost is that the README's images need the
published site to be up.

## D-11 — A column carries the verdict and its evidence together *(the three-column part is reversed by D-25)*

Point salad and the player-count poll each ship as three columns: the pill
alone, the measurement alone, and one column carrying the pill with its
numbers stacked under it. The combined column is the default, because a
verdict without its evidence is an opinion you cannot check, and a percentage
without its verdict makes you read two columns to learn one thing.

While a combined column is on, the two halves it already shows are disabled
in the picker rather than merely unticked — a checkbox you can tick that
changes nothing on screen reads as a bug in the page. `COLUMNS[].eats` names
what each combined column swallows, and the head script has its own copy in
`EATS`, because the first paint has to reach the same shape the page settles
on.

All three renderings are emitted into every row and CSS picks one, which is
what makes switching between them free of a re-render and keeps the choice
working for a reader with no JavaScript. One pair of mirrored functions draws
all of them — `pill_bar()`/`meter()` in `report.py` and
`pillBar()`/`meterHtml()` in the page script — so the variants cannot drift
apart. Within a cell it is two lines, not three: the pill, then the bar with
its figure small and right-aligned beside it, because the bar is what a
column of these is scanned by and the number is the footnote to it.

This replaced a single "At N / Best / Appr" trio and a radio button that
switched the salad column between bands and percentage. That radio was a
mode: a setting elsewhere in the menu that changed what a column meant. Three
columns you tick say the same thing without the indirection.

The player-count columns still stand down when the count is *Any*, since they
have nothing to read. What they no longer do is displace anything: choosing a
player count used to hide Win condition and Point salad to make room, which
silently took away two columns nobody had asked to lose.

## D-12 — A game link filters by id, not by name

Clicking a "people who like this also like" pill for a game you own puts
`id:<bgg id>` in the search box. A name is not an identity: filtering to
"Trickerion" by name matches every row that mentions it, and the gesture
means *this one game*. `id:` is a real search term rather than a hidden mode,
so it survives the URL, can be typed, and combines with words.

Deciding whether such a pill is owned at all follows the same rule. It was a
lowercase full-name lookup, which missed 43 chips across the collection: the
opinion database says "Trickerion" where the collection says "Trickerion:
Legends of Illusion", and "Chicago Express" where BGG files the same id as
"Wabash Cannonball". `bggids.py` has already resolved each name to an id, so
the id is matched first and the name only as a fallback. Matching on the part
before the colon was tried on paper and rejected: "Agricola" is not
"Agricola: Family Edition", and claiming you own a game you do not is worse
than an unnecessary link out.

## D-13 — Bands are defined once, in Python, and shipped to the page

Weight and time are banded, and the tables live in `report.py` as data:
`WEIGHT_BANDS` and `TIME_BANDS`, each row carrying its key, its name, its
upper edge, its pill class and its bar class. `main()` serialises them into
the page as `BANDS`, so the filter, the pill and the column all read the same
rows. Every other shared rule in this page is mirrored by hand between
`report.py` and `report_template.html` and has to be kept in step by comment;
these cannot drift because there is only one of them.

**Weight borrows BGG's vocabulary but cuts on the whole numbers.** Their Game
Weight poll names five points on the 1-5 scale — Light, Medium Light, Medium,
Medium Heavy, Heavy — and the API returns only the number, so the naming has
to happen here.

The cuts were the midpoints between those five anchors at first, which is how
BGG's own pages round a weight to a word. It reads wrong in a table: 3.86 and
4.36 both round to 4 and so both came out "Medium heavy", and a game plainly
over 4 sat under the same label as one well under it. Whole numbers are what
a reader assumes a 1-5 scale means — four and up is heavy — so that is what
these are, at the cost of dropping one of BGG's five names. The collection
divides 46/84/105/29.

**Time bands read the upper bound**, not the lower: at a game night the
question is how long this could run, not how quickly it could be over. "Very
long" starts at four hours.

## D-14 — Filters that take several values take them as a string

Interaction, point salad, weight and time are multi-select. Each is a hidden
`<input>` holding a comma-separated list, with `multiPick()` building the
control over it.

That shape was chosen so nothing else had to change. `F` is a map of things
with a `.value`, and the URL, the saved filters, Reset and `markFilters` all
read that one string; a `<select multiple>` would have needed every one of
them to learn what a multi-valued filter is, because `.value` on a multiple
select is just the first selected option. An empty value means the filter has
no opinion — the same thing the old "Any" option meant, without a magic
option sitting in the list pretending to be a value.

Two things this broke, both worth remembering. The filter wiring listens for
`input` on inputs and adds `change` only for `<select>`s, so a control
dispatching `change` on a hidden input updated its own caption and value
while the table sat still. And the saved-filter key had to go to v2: point
salad used to store the word "any" for no filter, which read back into the
new vocabulary is a band nothing is in, so a saved v1 would have opened the
page on an empty table.

## D-15 — The kind of interaction is computed from the model's own sentence

The level answers "do the players touch each other"; the kind answers "how" —
direct attacks, area control, a shared market, blocking, an auction. It is
computed, not asked for. The opinion pass already writes a sentence describing
the mechanism, and that sentence is the fact; `KINDS` in
`scripts/interaction.py` turns it into one of thirteen words by rules you can
read. Asking the model for the category directly would cost money to get
something less precise than the prose it already returns.

Order is the rule: the first pattern that matches wins, so the list runs from
the most particular kind to the most general. Two things that cost a
correction each, both worth keeping:

- **Area control sits above direct attacks.** "Area-majority fights over
  shared cities" is an area game, and putting attacks first filed every one of
  them under the word "fights".
- **"Fight" only counts where it is literal.** Players "fight over" a market
  or a spot in half the euros here, and reading that as combat filed Brass:
  Birmingham — "fighting over shared coal/iron markets and contested network
  links" — under direct attacks.

An expansion with no opinion entry of its own borrows its base game's, and a
game whose level came out Low and matched nothing is parallel play by
elimination — that is what Low means. Every game in the collection lands
somewhere: 47 blocking, 40 area control, 31 auction, 30 drafting, 27 direct
attacks, 24 shared market, 18 negotiation, 13 race, 11 co-op, 8 hidden roles,
8 parallel play, 4 shared actions, 4 paying rivals.

## D-16 — A fixed-width table spends its width on the game's name

Every column has a stated width and the name takes what is left, so widening
three columns by 36px each takes 108px off the name without touching its
rule. That is what happened when weight, time and interaction each grew to
hold a pill: "Brass: Birmingham" ended up stacked three words tall in a 72px
column.

Two things keep it honest now. Column widths are measured from the widest
pill the column can actually hold rather than guessed upward — and a header
still has to fit its own label, which is why "Winning score" needs 120px
however little the numbers under it need. And the name column has a stated
width of its own, so past the point where everything fits, the table scrolls
sideways in `.scroll` instead of crushing the one column you read every row
by.

## D-17 — A stacked column changes the whole table's rhythm

A cell carrying a pill over a second line is twice the height of a plain one,
and at the normal row padding the table closes up around it. So the rows are
given more air whenever any two-line column is on screen, and keep the tighter
spacing when every visible pill column is a single line — it is a property of
the view, not of the row.

`STACKED_COLS` names them, and like `OFF_BY_DEFAULT` and `EATS` it exists
three times: in `report.py` for the first paint, in the head script for a
browser with saved columns, and in the page script for every render after
that. The player-count columns only count while a count is chosen, since they
are hidden otherwise.

Within those columns the measurement under a pill stops at the width of the
widest pill in its own column, so the second line reads as belonging to the
first rather than running the width of the cell. Those caps are measured from
the rendered pill, not guessed.

## D-18 — "At N" sorts the way it reads, descending first

The combined column shows a pill over two percentages, so it sorts on all
three: the pill, then Best %, then Approved %. The key is built so that
*higher* is better and `verdict` is in `SORT_DESC_FIRST`, which means the
first click gives Best, then Good, then Plays — the order anyone clicking that
column wants — and ascending is the exact reverse of it.

One composite number rather than a comparator chain, because the sort reverses
a single value; a chain would have flipped only the first key. The percentages
are rounded first, because the column shows whole numbers and sorting on the
hidden decimals puts two rows that both read "79%" in an order the reader
cannot account for. Rounding also makes the weighting strictly lexicographic —
a pill step is worth 1,000,000 and a Best-percent step 1,000, against an
Approved term that never exceeds 100. Scaling the raw values instead let a
50-point Approved gap cancel a 1-point Best gap, and 3%/22% sorted ahead of
2%/72%.

## D-19 — 1280 is the page, and columns fit inside it

The page was widened to 1360 once, to make room for columns that had grown to
hold a pill. That is the wrong lever and it is now closed: 1280 is the width,
and a column set that will not fit is answered with a narrower column or one
fewer of them. Past 1280 the table stops being readable at arm's length and
the line lengths in the expanded row go with it.

## D-20 — Every column variant is a column; nothing is a mode *(reversed by D-25)*

The name column used to be one column plus a radio group choosing what rode
along with it, and `swallowedByGame()` special-cased Year and Designer against
that setting. It is now four columns — Game, Game+Year, Game+Designer,
Game+Year+Designer — and the rule that hides the others is the same `eats`
every other family uses: turning one on retires every column carrying a
subset of its fields, the standalone Year and Designer columns included.

One special case survives, and it earns its place: unticking all four would
leave a table of numbers with nothing to say which game each row is, so the
plain name comes back. Nothing else in the picker can empty a row like that.

## D-21 — A measured cell is two lines of fixed height

Both shapes — a pill over a bar, and a figure over a bar where a column has
no pill — are two lines of the same heights. The pill or the figure sits in a
23px box, the bar row in a 14px one, both set rather than inherited.

Both numbers are load-bearing. A pill carries vertical padding and a line
height of its own, so left alone its box and a plain figure's differ by a few
pixels. And cells are vertically centred, so a bar row carrying a figure
beside it and one carrying a bare track centre differently and push the line
above them apart. Fixing both is what lets a row read straight across: every
pill and number on one line, every bar on the next, whichever variant each
column happens to be showing.

## D-22 — Derived vocabularies belong in the property picker

Win condition and interaction kind were multi-select filters of their own for
about an hour. They are now categories in the one property field, beside
traits, categories, mechanics, designers and families — because that is what
they are: a vocabulary a game carries, not a scale it sits on. The filter row
is shorter for it, and the property field is the one place to look for "what
is this game".

`annotate()` hangs both on each game before the index is built. Neither is a
list BGG gives us — how a game is won is computed by `scoring.py` from the
facts the opinion pass reports, and the kind of interaction by
`interaction.py` from the sentence it writes — but by the time the picker is
built they are ordinary lists of names and nothing downstream needs to know
the difference.

## D-23 — An ordered axis is a range over its own number

Interaction, point salad, weight and time were multi-selects for a while. All
four are *ordered* — light to heavy, short to very long, low to high — and
what you actually want from an ordered scale is a span: everything up to 90
minutes, medium weight or heavier. A tick-list made you say that by ticking
every band you meant and re-ticking when you changed your mind, and it let you
ask for nonsense like "light or heavy but nothing between".

Each is a two-handled range now, and the range is over the **underlying
number**, not over a list of bands: weight is 1-5, time is minutes, point
salad is its 0-100 score. The bands only name stretches of that number —
their edges are the dots you can land on and their names the labels beside
them. That keeps the precision the number has while reading in the vocabulary
the columns use, and it is why the numeric Weight and Time boxes under *More
filters* could go: this is them, legibly. Interaction is the exception and
snaps, because Low, Medium and High is all a game can be.

The control is a dropdown that looks like every other one until you open it,
and the slider inside is **vertical**. That is not decoration: the band names
are horizontal text, and a vertical track lets each one read straight across
from the stretch it belongs to, which no horizontal scale can do without
turning the text on its side.

Two details cost a correction each. The track stops at four hours and the top
handle then means "and over", or a wide-open slider quietly drops the
480-minute games off the end. And it is built on pointer events rather than
two rotated `<input type=range>`: rotation makes the hit area lie about where
it is, and two of them overlapping left the lower handle unreachable at the
top of the scale.

The numeric Weight and Time ranges under *More filters* went with this. They
covered the same ground through a different door and nothing kept the two in
step, so they could disagree about what the table was showing.

The captions name the bands at the ends rather than saying "up to" and "and
over": against names that are already phrases, "Up to Within 90 min" is not a
sentence, and "Short to Within 90 min" is.

## D-24 — A description belongs to a vocabulary, not to a word

Tag descriptions were keyed by bare name, which was fine while every tag came
from BGG. It stopped being fine when win conditions and interaction kinds
joined the picker: *Race* is a BGG mechanic ("first to the end of a track
wins") and also an interaction kind (everyone pushing for one finish), and the
bare lookup gave the interaction kind a description of a win condition.

`tag-descriptions.txt` now takes an optional `kind:Name` key, which wins over
the bare name where it exists. Every win condition and every interaction kind
has one.

## D-25 — How much of a cell to show is one setting, not four columns each

D-11 and D-20 pushed every rendering into the column list: Time, Weight,
Interaction, Point salad and the player count each appeared as "band and
number", "band only" and "number only", and the name column as four variants.
The argument was that a setting elsewhere in the menu which changes what a
column *means* is indirection worth removing.

At four columns' worth of variants it was defensible. At thirty-four columns
it was not: twelve entries in the list said four things, the list needed three
CSS columns to fit, asking for numbers everywhere meant finding and reticking
four separate rows, and `eats` existed only to stop you asking for the same
number twice in adjacent columns.

It is now one column per thing measured, and two settings beside the list:
**Cells** (detailed or compact) and **Game column** (which of year and
designer ride under the name). The distinction D-20 drew is
still the right one — these are not modes that change what a column *means*,
they change how much of the same fact it prints — and one of them governs
every such column at once, which is what makes it a setting rather than a
column.

**Cells** started as three choices — only pills, only numbers, pills and
numbers — and settled at two. "Only pills" and "only numbers" were the same
request stated twice: one line per cell rather than two. Which line to keep is
a property of the column, not a thing to ask about. Every column with a figure
shows the figure, because "3.86" is shorter than "Medium" and says more; the
two whose figure needs explaining keep their pill instead — the kind of
interaction is prose and has no figure at all, and point salad's band name
says in a word what its 0-100 score says in a number nobody has memorised.
`keep_pill` in `pill_bar()` marks those two.

Compact is a row height as much as a cell shape: one line per cell means the
tight row padding and the small covers, which is most of what makes the table
feel dense.

The mechanism is unchanged and is what makes this cheap: every cell still
ships all of its parts and the stylesheet paints the ones asked for, so
switching costs no re-render, cannot make two columns disagree about which
line they draw on, and still works for a reader with no JavaScript. What
changed is that the switch is one class on `<html>` (`det-detailed` or
`det-compact`) instead of twelve `off-` classes. `swallowedByGame()` comes back
with the Game column, and `eats`/`lockedReason` go: nothing else in the picker
needs the interlock now.

The report lost 490 KB of markup in the bargain — the twelve columns were
rendered into all 265 rows whether or not anyone had them on.

Two presets went with them. "Only pills" and "Only numbers" were column sets
that existed to swap four columns for four others; as a setting it composes
with the remaining presets instead of competing with them, and no longer
resets the rest of the table on the way past.


## D-26 — Fit is a fact about the question, not about the game

Every other column states something about a game that would be true if
nobody were looking: its weight, how long it runs, what the poll said. **Fit**
states how well a game answers *what the filters are currently asking*, which
makes it a different kind of thing, and the design follows from that.

It is computed in the browser rather than in the build, because the build does
not know the question. It cannot be filtered on, because it is derived from
the filters and a filter over its own inputs is a loop. And sorting by it
shows the whole collection: the filters stop being a gate and become the
criteria being scored against, so a game that misses on one axis still has a
place in the ranking — hiding it would be hiding the second-best answer.

The score is a weighted mean of the axes that are actually set, each scored
0-1, so with nothing set the column is a ranking by quality alone. Being
outside a range is a distance rather than a zero: `FIT_TOL` says how far
outside is worth nothing — a point and a half of weight, ninety minutes of
play, forty points of salad, two levels of interaction. The ratings go in on
separate scales, because a BGG average of 8.6 is extraordinary while a
personal 8.6 is not, and both count where both exist.

The numbers are a starting point, not a finding: the weights in `FIT_W` say
that the player count matters more than the point-salad score, which is a
preference, not a fact. They are meant to be argued with.

## D-27 — Ranking is a switch, not a column you have to find

Fit started as a column in the picker, which put the interesting part — the
table stops hiding things and starts ordering them — behind a checkbox in a
menu, indistinguishable from "Price paid". It now has a switch beside *More
filters*, **Rank by fit**, which shows the column and sorts by it in one
gesture; the column itself moved to the end of the table and sits below a
line of its own in the picker, because it is the one column that is about the
question rather than about the game.

The traffic lights came from the same thought. A single number is a verdict
you cannot argue with, so every cell that fed it is tinted while the table is
ranked — green where the game answered that column, amber for a near miss,
red for a failure — in the pill colours the table already uses. The classes
are painted whether or not ranking is on and the stylesheet only shows them
while it is, so switching does not mean repainting 265 rows.

Whether you have *played* it carries the most weight of any axis (2.4 against
1.6 for the player count). "Something we have never got to the table" and
"the one we keep coming back to" are different requests, and a game that
answers the wrong one is the wrong game however well it scores elsewhere.

