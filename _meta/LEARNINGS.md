# Traps

Most of these look like bugs in the data and are bugs in how it was measured.

## A single sample of a judged axis is a draw, not a reading

Ask the same model the same question about the same 26 games three times and
the answers move: a 0-100 judgement shifts by a **median of 7 points, a mean
of 9-10, and as much as 32** on a contested game. Labels flap on 6 to 11 of
26 games between runs.

Games with a settled reputation barely move (Dune 92/91/92, War of the Ring
87/88/88). Contested ones swing wildly (Root 57/58/84, Patchwork on the
interaction axis 58/26/32).

Two wrong conclusions were drawn from single samples during one session:

- A full-collection pass appeared to score 19/26 when the prompt reproducibly
  scores 22. The 19 was a *different* bug (below), but the single sample made
  it look like the prompt.
- A prompt fix appeared to have "moved the errors around" when it had
  actually improved 3/5 to 4/5; the game that looked like a regression was a
  bad draw from a distribution centred 23 points higher.

**Never compare two prompts, or report a score, from one run each.**
`enrich.py --samples N` asks N times and keeps the median of the graded
fields, ordinal or numeric. Use 3 when calibrating; 1 is fine for a normal
run, because answers are cached once and committed.

## A failed batch silently poisons the database

`enrich.py --force` only writes on success. So when a batch fails, those
games keep whatever an *earlier, differently-prompted* pass said, and the
database quietly becomes a mixture of schemes that no test can see. A full
run once lost 25 of 242 batches to empty responses and the resulting mixture
scored three points worse than either scheme alone.

`ask()` now tolerates fences and preamble, retries three times, and fails
fast on an error envelope. If you add a pass, do not reintroduce a bare
`json.loads` of the model's reply.

Related: a non-forced run decides what to skip by looking for a field the
current pass writes. If you change a prompt's output shape, change the skip
check too, or a plain run will skip every record that is on the *old* scheme
— exactly the ones worth re-asking.

## Ten times the money bought nothing

Web search with forced citations was measured against three offline schemes
on the same 26 games. It cost about **$0.13 a game against $0.013** and
scored no better — 21/26 against 22/26 for the best offline prompt. Grounding
was not the bottleneck; prompt *ordering* was. Asked for a verdict first, the
model reasons from weight and table presence; asked what players *call* the
game first, it reaches for the phrase, and the phrase is usually right.

Web lookups are still the right answer for a genuinely unknown game — one
published after the training cutoff, where the alternative is invention, not
vagueness. They are the wrong answer for a judgement about a well-known game.

## Some disagreements are real and cannot be fixed

Three or four games survive every scheme: the community phrase the model
quotes is genuinely the community's, and the owner disagrees with it.
Everyone calls Scythe and Patchwork multiplayer solitaire except him. That is
the ceiling of any community-grounded method, and the right response is to
record the call in `tests/` and leave the rule alone, not to special-case the
game.

## The measurement harness must read the same data the page does

See `ARCHITECTURE.md`: the checks read `data/ai/`, the page reads
`data/games.json`. Forgetting the second `build.py` produces a page and a
score that disagree, with no error.

## Browser things that only break when you actually click

- `replaceState` in a re-render triggered by `popstate` overwrites the entry
  you just navigated to and destroys everything forward of it. Back works,
  forward silently does nothing. Suppress URL writes while applying a view
  from history.
- A composite gesture — one that changes filters *and* opens a game — must be
  one history step. Done naively the render in the middle replaces the entry
  you came from, and going back lands on a filtered table instead of the
  game.
- A hash-only history move fires **both** `popstate` and `hashchange`. Wire
  both to one guarded function.
- Navigating to a URL that differs only by its hash is a *same-document*
  navigation: the page does not reload. A restore test written that way
  proves nothing. Force a real reload.
- Game ids arrive from the server as strings and come out of a URL as
  strings. A stray `Number()` on one side matches nothing.
- A `var` shadows a function declaration for the whole scope. Naming a helper
  `fold()` collided with a local `var fold` and turned every search into "not
  a function", silently matching every row.
- Flex centring centres the *line box*, not the glyphs: digits sit visibly
  high because the line box reserves descender space they do not use.

## Performance, if the collection ever gets large

Measured with synthetic collections: at 10,000 games the browser spends
740-980ms laying out a 647,000px-tall table per render, while the page's own
JavaScript takes about 120ms of that. Sorting is 541ms, a keystroke 32-84ms,
the file 63MB. The fix is to render fewer rows — cap at a few hundred with a
"show the rest" — not to optimise the script. At the real size (~265) none of
this matters.
