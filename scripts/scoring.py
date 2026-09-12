#!/usr/bin/env python3
"""How a game is won, and how much of a point salad it is.

Both used to be labels the model was asked for directly, and both came out as
vibes: Food Chain Magnate, whose only currency is money, was filed as "Broad",
while Rajas of the Ganges — four separate tallies — was "Some". So the model
is no longer asked for the label. It reports *facts* about the game that can be
checked (see FACTS below), and the label is computed here, by rules anyone can
read and argue with.

The rules encode a handful of signals:

* **Separate subsystems, not scoring lines.** Carcassonne scores cities, roads,
  monasteries and farms, but they all come out of one act of placing a tile and
  a meeple: one subsystem, not four. Rajas of the Ganges really does run
  several minigames side by side.
* **What the winning score looks like.** A game won with 10 points is a race;
  a game won with 180 is an accumulation. Scores in the single digits or low
  tens cannot be a salad whatever else is true.
* **When the points are counted.** Everything tallied at the end is the salad
  feeling; a running score you watch tick along is less so.
* **What shape the score is.** A single currency, a count of objectives, the
  *lowest* of your categories, or a contest over shared majorities are all
  ways of not being a salad, however many things feed them.
* **How the game ends.** A target score is a race. A game that usually ends on
  a sudden-death condition is not really decided by its tally at all — as
  opposed to one where finishing something merely stops the clock and the
  points still decide, which is an ordinary points game.
"""

# The fact block the opinion pass fills in, documented for the prompt.
FACTS = {
    "subsystems": "the separate scoring engines a player builds, each with its "
                  "own rules and economy — not the lines on the scorepad",
    "sources": "the categories the rules actually total at the end",
    "winning_score": "what a winning score typically looks like, as a number",
    "tally": "running | endgame | mixed",
    "shape": "sum | single_currency | objective_count | lowest_category | "
             "majority_control",
    "ends_by": "target_score | end_trigger | fixed_length | exhaustion | "
               "sudden_death | elimination | coop_goal",
    "sudden_death_common": "true when games usually end on that condition "
                           "rather than by running out",
}

SALAD_ORDER = ["no", "touch", "lot", "total"]
SALAD_LABEL = {
    "no": "No, sharp focus",
    "touch": "Just a touch",
    "lot": "Quite a lot",
    "total": "Total point salad",
}
# The column has less room than the dropdown.
SALAD_SHORT = {"no": "No", "touch": "A touch", "lot": "Quite a lot",
               "total": "Total salad"}
SALAD_PILL = {"no": "p3", "touch": "p2", "lot": "p1", "total": "pw"}

WIN_ORDER = ["race", "points", "money", "lowest", "majority", "sudden",
             "coop", "elimination", "other"]
WIN_LABEL = {
    "race": "Race to a target",
    "points": "Most points at the end",
    "money": "Most money",
    "lowest": "Highest of your lowest",
    "majority": "Majority control",
    "sudden": "Sudden-death condition",
    "coop": "Cooperative goal",
    "elimination": "Last player standing",
    "other": "Other",
}
WIN_SHORT = {
    "race": "Race", "points": "Most points", "money": "Money",
    "lowest": "Highest-lowest", "majority": "Majority", "sudden": "Sudden death",
    "coop": "Co-op goal", "elimination": "Elimination", "other": "Other",
}

# A target reached this early is a race, whatever else the game is doing.
RACE_SCORE = 35
# Below this, the winning score is too small to be an accumulation.
SMALL_SCORE = 25


def _step(level, by):
    i = max(0, min(len(SALAD_ORDER) - 1, SALAD_ORDER.index(level) + by))
    return SALAD_ORDER[i]


def _cap(level, ceiling):
    return level if SALAD_ORDER.index(level) <= SALAD_ORDER.index(ceiling) \
        else ceiling


def salad(f):
    """How much of a point salad, from the facts. Returns a SALAD_ORDER key."""
    if not f:
        return None
    shape = (f.get("shape") or "sum").strip()
    ends = (f.get("ends_by") or "").strip()
    score = f.get("winning_score")
    subs = [s for s in (f.get("subsystems") or []) if s]
    tally = (f.get("tally") or "mixed").strip()

    # One currency, a count of objectives, your lowest category, or a fight
    # over shared majorities: none of these are salads however many things
    # feed them.
    if shape in ("single_currency", "objective_count", "lowest_category",
                 "majority_control"):
        return "no"
    if ends == "coop_goal":
        return "no"
    # A target reached at 10 or 30 points is a race, not an accumulation.
    if ends == "target_score" and isinstance(score, (int, float)) \
            and score <= RACE_SCORE:
        return "no"
    srcs = [s for s in (f.get("sources") or []) if s]
    if len(subs) <= 1:
        # One engine: the scorepad may still list several lines — Brass totals
        # links and industries, Carcassonne cities, roads, farms — but they all
        # come out of the same act. A touch of salad at most, and none at all
        # when there is really only one line.
        return "no" if len(srcs) <= 1 else "touch"

    level = {2: "touch", 3: "lot"}.get(len(subs), "total")
    # Counting everything at the end is the salad feeling, so it promotes. A
    # running score does not demote: Rajas of the Ganges advances two markers
    # in plain sight and is still three minigames bolted together.
    if tally == "endgame":
        level = _step(level, 1)
    if f.get("sudden_death_common"):
        level = _step(level, -1)
    if isinstance(score, (int, float)) and score <= SMALL_SCORE:
        level = _cap(level, "touch")
    return level


def win(f):
    """What decides the winner. Returns a WIN_ORDER key."""
    if not f:
        return None
    shape = (f.get("shape") or "").strip()
    ends = (f.get("ends_by") or "").strip()
    if ends == "coop_goal":
        return "coop"
    if ends == "elimination":
        return "elimination"
    if shape == "single_currency":
        return "money"
    if shape == "lowest_category":
        return "lowest"
    if shape == "majority_control":
        return "majority"
    if ends == "target_score":
        return "race"
    if ends == "sudden_death":
        return "sudden"
    if shape in ("sum", "objective_count"):
        return "points"
    return "other"


def sudden_death(f):
    """Whether a game that is decided on points can also end out of nowhere."""
    return bool(f and f.get("sudden_death_common")) and win(f) != "sudden"
