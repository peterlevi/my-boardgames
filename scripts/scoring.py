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
    "sources": "every line you would write on a scorepad",
    "winning_score": "what a winning score typically looks like, as a number",
    "tally": "running | endgame | mixed",
    "shape": "sum | single_currency | objective_count | lowest_category | "
             "majority_control",
    "ends_by": "every ending the rules have, most common first: target_score "
               "| end_trigger | fixed_length | exhaustion | sudden_death | "
               "elimination | coop_goal",
}

# Words that mark a scoring line as optional rather than part of the game.
OPTIONAL = ("variant", "expansion", "module", "promo", "mini-exp")
# Qualifiers that split one category across eras, rounds or colours.
import re as _re

_ERA = _re.compile(r"[,(]?\s*\b(canal|rail|first|second|third|final|each)?\s*"
                   r"(era|round|age|phase|scoring)\b.*$", _re.I)
# The same category scored in two eras is written "canal links", "rail links".
_ERA_PREFIX = _re.compile(r"^\s*(canal|rail|first|second|third|final)\s+", _re.I)
_PAREN = _re.compile(r"\([^)]*\)")
# Sweeping the table into points at the end is not a category of its own.
# "One currency" only means money when the categories actually name money:
# Dune: Imperium's single currency is victory points, Food Chain Magnate's is
# cash, and the two want opposite answers.
_MONEY = _re.compile(r"\b(money|cash|coins?|profit|dividends?|credits?|loot|"
                     r"gold|wealth|capital|net worth|share value|shares?|"
                     r"stock)\b|[£$]", _re.I)
_LEFTOVERS = _re.compile(
    r"(leftover|left-over|unused|spare|remaining)\s+\w*\s*"
    r"(money|cash|coins?|resources?|goods|workers?)|money[- ]to[- ]vp", _re.I)


def is_money(f):
    """Whether a single-currency game is really played for money."""
    text = " ".join(str(x) for x in ((f or {}).get("sources") or []))
    return bool(_MONEY.search(text))


def categories(f):
    """The distinct things a game scores, from the list the facts carry.

    The facts are written exhaustively on purpose, which means the same
    category turns up once per era — Brass scores links and industries in the
    canal era and again in the rail era, and that is two categories, not four
    — while optional variants, expansion modules and the end-of-game sweep of
    leftover money into points ride along with them. All of it is folded away
    here rather than in the prompt, because a list is easier to normalise than
    a judgement is to elicit.
    """
    out, seen = [], set()
    for raw in (f or {}).get("sources") or []:
        text = str(raw or "").strip()
        if not text or any(w in text.lower() for w in OPTIONAL):
            continue
        if _LEFTOVERS.search(text):
            continue
        key = _ERA_PREFIX.sub("", _ERA.sub("", _PAREN.sub("", text)))
        key = key.strip(" ,;–-").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(text)
    return out


SALAD_ORDER = ["no", "touch", "lot", "total"]
SALAD_LABEL = {
    "no": "No, sharp focus",
    "touch": "Just a touch",
    "lot": "Quite a lot",
    "total": "Total point salad",
}
# The column has less room than the dropdown.
SALAD_SHORT = {"no": "No", "touch": "A touch", "lot": "Quite a lot",
               "total": "Point salad"}
SALAD_PILL = {"no": "p3", "touch": "p2", "lot": "p1", "total": "pw"}

WIN_ORDER = ["race", "points", "objectives", "money", "lowest", "majority",
             "sudden", "coop", "elimination", "other"]
WIN_LABEL = {
    "race": "Race to a target",
    "points": "Most points at the end",
    "objectives": "Enough objectives",
    "money": "Most money",
    "lowest": "Highest of your lowest",
    "majority": "Majority control",
    "sudden": "Sudden-death condition",
    "coop": "Cooperative goal",
    "elimination": "Last player standing",
    "other": "Other",
}
WIN_SHORT = {
    "race": "Race", "points": "Most points", "objectives": "Objectives",
    "money": "Money",
    "lowest": "Highest-lowest", "majority": "Majority", "sudden": "Sudden death",
    "coop": "Co-op goal", "elimination": "Elimination", "other": "Other",
}

# A target reached this early is a race, whatever else the game is doing.
RACE_SCORE = 35
# The bands a winning score falls into: too small to accumulate, modest,
# substantial, and the three-figure totals that give the game away.
SMALL_SCORE = 25
MID_SCORE = 45
BIG_SCORE = 90


def _step(level, by):
    i = max(0, min(len(SALAD_ORDER) - 1, SALAD_ORDER.index(level) + by))
    return SALAD_ORDER[i]


def _cap(level, ceiling):
    return level if SALAD_ORDER.index(level) <= SALAD_ORDER.index(ceiling) \
        else ceiling


def endings(f):
    """Every way the game can end, most common first, as (how, decided_by)
    pairs. Three shapes of record read the same from here: the newest carries
    `endings` as pairs, older ones a list of `ends_by` strings, oldest a
    single string."""
    f = f or {}
    pairs = f.get("endings")
    verified = f.get("ends_by") if f.get("checked") else None
    if isinstance(verified, str):
        verified = [verified]
    if verified and isinstance(pairs, list) and pairs:
        # A record read off a rules page keeps its own endings; the later pass
        # is only allowed to say what settles each of them.
        by = {}
        for pr in pairs:
            if isinstance(pr, dict) and pr.get("how"):
                by[pr["how"]] = pr.get("decided_by") or ""
        pairs = [{"how": h, "decided_by": by.get(h, "")} for h in verified]
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        out = []
        for p in pairs:
            how = (p.get("how") or "").strip()
            by = (p.get("decided_by") or "").strip()
            if how and (how, by) not in out:
                out.append((how, by))
        return out[:3]
    ends = f.get("ends_by") or []
    if isinstance(ends, str):
        ends = [ends]
    seen, out = set(), []
    for e in ends:
        e = (e or "").strip()
        if e and e not in seen:
            seen.add(e)
            out.append((e, ""))
    return out[:3]


def how_ends(f):
    """Just the endings, without what settles them."""
    return [how for how, _ in endings(f)]


def salad(f):
    """How much of a point salad, from the facts. Returns a SALAD_ORDER key.

    The backbone is the owner's own heuristic: when the highest score wins and
    winning totals run into the high tens or hundreds, purely additive, never
    zero-sum, that is the signal. Everything else adjusts it — how many
    separate engines feed the total, how many lines the rules add up, whether
    it is all counted at the end, and whether the game even goes the distance.
    """
    if not f:
        return None
    shape = (f.get("shape") or "sum").strip()
    ends_all = how_ends(f)
    ends = ends_all[0] if ends_all else ""
    score = f.get("winning_score")
    score = score if isinstance(score, (int, float)) and score > 0 else None
    subs = len([x for x in (f.get("subsystems") or []) if x])
    srcs = len(categories(f))

    if "coop_goal" in ends_all:
        return "no"
    # One currency out of one or two engines is a money game, not a salad —
    # Food Chain Magnate, 1846. Four engines funnelling into money is not:
    # The Gallerist pays you for art, reputation, influence and contracts.
    if shape == "single_currency" and is_money(f) and subs <= 2:
        return "no"
    # Counting objectives is not accumulating points, however many kinds of
    # objective there are.
    if shape == "objective_count":
        return "no"
    if shape == "majority_control" and srcs <= 1:
        return "no"
    # A target reached at 10 or 30 points is a race.
    if ends == "target_score" and score is not None and score <= RACE_SCORE:
        return "no"
    if subs <= 1 and srcs <= 1:
        return "no"
    # Nobody calls a game won with eight points a salad, whatever is on the
    # scorepad: Biblios totals five categories and ends at three.
    if score is not None and score <= SMALL_SCORE:
        return "no"

    if score is None:
        level = "touch" if subs <= 2 else "lot"
    elif score < MID_SCORE:
        level = "touch"
    elif score < BIG_SCORE:
        level = "lot"
    else:
        level = "total"

    if srcs >= 4:
        level = _step(level, 1)
    if subs >= 3:
        level = _step(level, 1)
    if (f.get("tally") or "").strip() == "endgame":
        level = _step(level, 1)

    # A game that can end on a condition is not really decided by its tally,
    # wherever that ending sits in the list.
    if "sudden_death" in ends_all:
        level = _cap(level, "touch")
    # So are two lines on the scorepad out of two engines, however big the
    # numbers on them get: Brass wins with 180 points from exactly two
    # interdependent tallies, links and industries, and nobody calls that a
    # salad.
    if srcs <= 2 and subs <= 2:
        level = _cap(level, "touch")
    # Few categories, however big the numbers on them: Brass wins with 170
    # points out of links and industries, and nobody calls that a salad. The
    # top of the scale is reserved for games that really do pay you for four
    # different things — a big number on its own is not enough.
    if srcs <= 2:
        level = _cap(level, "touch")
    elif srcs == 3:
        level = _cap(level, "lot")
    # Contested or minimum-of scores are not accumulations.
    if shape in ("lowest_category", "majority_control"):
        level = _cap(level, "lot")
    return level


def _win_for(end, by, shape, fallback="", money=True):
    """One ending, as a way of winning. `by` is what the rules say settles it;
    the score's shape stands in when a record does not say."""
    if end == "coop_goal":
        return "coop"
    if end == "elimination":
        return "elimination"
    if by == "instant" or (not by and end == "sudden_death"):
        return "sudden"
    from_shape = {"single_currency": "money" if money else "points",
                  "lowest_category": "lowest",
                  "majority_control": "majority",
                  "objective_count": "objectives"}.get(shape, "points")
    # "Points" is the vaguest answer there is, so the score's own shape wins
    # over it: Sekigahara's points are control of castles, Food Chain
    # Magnate's are money, Tigris & Euphrates' are your weakest colour.
    # An ending that merely stops the game is settled the same way as the
    # rest of the game unless it says otherwise: Dune: Imperium runs out of
    # conflict cards and still counts the same victory points.
    if not by and fallback:
        by = fallback
    settles = from_shape if by in ("", "points") else by
    # Reaching a threshold first is a race — unless what you are racing to
    # collect is objectives, which is Innovation's achievements.
    if end == "target_score":
        return "objectives" if settles == "objectives" else "race"
    return {"points": "points", "money": "money", "objectives": "objectives",
            "majority": "majority", "lowest": "lowest"}.get(settles, "points")


def wins(f):
    """Every way the game can be won, most common first — plenty of games have
    two or three, and forcing Innovation to choose between its achievements,
    its dogma wins and its points was losing most of the answer."""
    if not f:
        return []
    shape = (f.get("shape") or "").strip()
    ends = endings(f) or [("", "")]
    fallback = next((by for _, by in ends if by and by != "instant"), "")
    money = is_money(f)
    out = []
    for how, by in ends:
        w = _win_for(how, by, shape, fallback, money)
        if w not in out:
            out.append(w)
    return out[:3]


def win(f):
    """The main way to win, for sorting and for a one-word column."""
    ws = wins(f)
    return ws[0] if ws else None
