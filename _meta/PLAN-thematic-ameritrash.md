# Two more axes: thematic fit, and euro vs ameritrash

Status: **measured on a 20-game probe, not yet run over the collection.**
The prompts are in `scripts/enrich.py` (`--theme`, `--style`) and work; what
is left is a full run, a reference file of the owner's calls, and the columns.

## Why these two are different problems

`Point salad` is *computed* — the model reports facts about how a game scores
and `scripts/scoring.py` turns them into a number. There is no sampling noise
in it at all.

`Interaction` is *judged*, and the pipeline that works for it asks for the
community's own words before the verdict. Both new axes are judged, so they
inherit that design and its noise.

`Euro vs ameritrash` is the lucky one: BGG already sorts its own games into
sections, and those are cached in `data/raw/things/*.xml` and surface as
`types` on every game. This collection carries 203 **Strategy Game**, 46
**Family Game**, 15 **Party Game**, 11 **Thematic**, 9 **War Game** and 8
**Abstract**. That is a free validation set — no reference file needed to
know whether the axis is behaving.

## What the probe measured

20 games: the five the owner named, plus every Thematic- or Wargame-ranked
game in the collection. Cost $0.30 per pass.

### Euro to ameritrash (0 = pure euro, 100 = full ameritrash)

**17 of 20 agree with BGG's own section.** All five euros land euro-side —
Brass 10, Barrage 15, Hansa Teutonica 20, El Grande 28, Food Chain Magnate 32
— and the thematic games land ameri-side: Gloomhaven 85, Twilight Imperium
76, Robinson Crusoe 75, Star Wars: Rebellion 72, Dune 72, War of the Ring 70,
Root 65.

The three that disagree are interesting rather than wrong. **High Frontier 4
All** scores 15 against BGG's Thematic filing — "a simulation with a game
bolted on" is a fair description of a hard-science euro. **Mysterium** (45)
and **Undaunted** (48) sit on the fence, which is defensible for both.

This axis looks ready.

### Thematic fit of the mechanics (0 = pasted on, 100 = inseparable)

The first prompt scored **3 of 5** against the owner's calls, and the reason
was a defect worth recording. It marked Food Chain Magnate down to 36 while
its own explanation described the wage cascade where *you pay every
subordinate whether or not they produced anything* — which is exactly how a
franchise payroll works. It had read community talk about theme **tone**
("a joke theme", "the burgers are just flavour text", "Victorian clothes") as
evidence about mechanical **fit**. Players use "pasted on" for both, and they
are different claims.

The prompt now separates them explicitly: the question is only what the rules
do, a joke theme can fit perfectly, a lavish production can be generic
underneath, and the test is whether somebody who knows the real subject would
recognise the rules as a model of it. "Pasted on" is discounted unless the
complaint is plainly about rules. The two calibration examples in the prompt
are stated as general principles — business-simulation rules versus
interchangeable network-and-majority puzzles — so no specific game is
hardcoded.

With that prompt, averaged over three samples, it scores **4 of 5**:

| game | owner | mean of 3 | samples |
|---|---|---|---|
| Food Chain Magnate | high | 92 | 91, 94, 91 |
| Barrage | high | 71 | 76, 68, 68 |
| Brass: Birmingham | high | **48** | 52, 54, 37 |
| Hansa Teutonica | low | 11 | 12, 10, 12 |
| El Grande | low | 19 | 18, 18, 22 |

**Brass is a genuine disagreement, not a bug.** The model grants that coal and
iron being consumed by connected links models real depletion, but calls the
link-auction and the VP plumbing generic. That belongs in a reference file as
a judgement, not in the prompt.

## The measurement trap, recorded because it was fallen into twice

Single samples of a 0-100 judged axis are draws, not readings. Theme spread
over three samples: **median 7, mean 8.2, max 27**. Interaction, measured the
same way: median 7, mean 9.7, max 32.

Games with a settled reputation barely move — Dune 92/91/92, War of the Ring
87/88/88, Food Chain Magnate 91/94/91. Contested ones move enormously — Root
57/58/84, Brass 52/54/37, Patchwork (on the interaction axis) 58/26/32.

Both times a conclusion was drawn from one sample it was wrong. A full
collection pass appeared to score 19/26 on interaction when the prompt
reproducibly scores 22; a prompt fix appeared to have "moved the errors
around" on theme when it had in fact improved 3/5 to 4/5 and Barrage's
"collapse" to 48 was a bad draw from a distribution centred on 71.

**Rule: never compare two prompts, or report a score, from single samples of a
judged axis.** `enrich.py --samples N` exists for this and now takes the
median of numeric fields as well as ordinal ones.

## What is left

1. Run both passes over all 242 games at `--samples 3`. Measured cost is
   ~$0.013 a game a sample, so roughly **$9.50 per axis, $19 for both**.
   Single-sample would be ~$6.50 for both but hands back numbers that move
   ±8 and occasionally ±27.
2. Add `tests/theme_calls.txt` in the shape of `tests/interaction_calls.txt`,
   seeded with the five calls above, and extend `scripts/check_interaction.py`
   (or a sibling) to score it. Brass is the open question to settle first.
3. Columns for both axes, with the same number-or-band choice the point-salad
   column now has.
4. For euro/ameritrash, consider showing BGG's own section alongside the
   number, since it is free, factual, and already in `types`.

## Known-good defaults if this is picked up cold

- Batch 7-8 games per `claude` call; the agent boot dominates, not the
  thinking.
- Never use `--online` for a judged axis. On interaction it cost ten times as
  much and scored no better than the free pass.
- Ask for the evidence before the verdict. Asked for a level first, the model
  reasons from weight and table presence; asked what players *call* the game
  first, it reaches for the phrase, and the phrase is usually right.
