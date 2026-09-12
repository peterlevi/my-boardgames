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


def score_range(f):
    """The range a winning score typically falls in, or None where a score is
    not what decides the game — a cooperative goal, a last player standing, a
    sudden-death condition. Optional: it is only there if the enrichment pass
    has been run with --scores."""
    rng = (f or {}).get("score_range")
    if not isinstance(rng, list) or len(rng) != 2:
        # The range pass may have skipped a game the facts already carry a
        # winning score for — better a single honest number than a blank.
        one = (f or {}).get("winning_score")
        if isinstance(one, (int, float)) and one > 0:
            return (int(round(one)), int(round(one)))
        return None
    try:
        lo, hi = float(rng[0]), float(rng[1])
    except (TypeError, ValueError):
        return None
    if lo <= 0 and hi <= 0:
        return None
    lo, hi = min(lo, hi), max(lo, hi)
    return (int(round(lo)), int(round(hi)))


def score_text(f):
    """That range as it reads in a column: "130–170", or "10" when it is a
    single number, or "" when the game is not won on a score."""
    rng = score_range(f)
    if not rng:
        return ""
    lo, hi = rng
    return str(lo) if lo == hi else f"{lo}\u2013{hi}"


def score_sort(f):
    """Where the range sits, for sorting: its midpoint."""
    rng = score_range(f)
    return None if not rng else (rng[0] + rng[1]) / 2


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


# Interaction is NOT computed here, and the attempt is worth recording. Five
# facts — a shared board, blocking on it, acting on an opponent, a common
# market, negotiation — were weighed into Low/Medium/High, which fixed The
# Quest for El Dorado (a race down a shared board that the model called Low)
# and broke almost everything else: Ra, High Society and Medici came out Low,
# because an auction has no board and no blocking, only a pool — and bidding
# against each other is the most interactive thing in them. Food Chain
# Magnate, Bus and The Great Zimbabwe dropped to Medium; Terraforming Mars and
# Scythe rose to High. The model's own holistic level was better on every one
# of those, so the report uses it. Whatever replaces it has to account for
# auctions, and for the difference between a shared board you race on and one
# you fight over.
IX_ORDER = ["Low", "Medium", "High"]

SALAD_ORDER = ["no", "touch", "lot", "total"]
SALAD_LABEL = {
    "no": "No, sharp focus",
    "touch": "Just a touch",
    "lot": "Quite a lot",
    "total": "Yes, point salad",
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


def salad_score(f):
    """How much of a point salad, as 0-100 rather than one of four words.

    Every ingredient is already in the facts the model reports, and the
    four-way label was only ever these numbers collapsed early: how big a
    winning score is, how many categories the rules total, how many separate
    subsystems feed them, and whether it is all counted at the end. Computing
    the number first and bucketing it afterwards costs nothing extra — there
    is no second model call and no sampling noise, because this is arithmetic
    over facts, not a judgement — and it makes how many bands the report shows
    a presentation choice rather than a property of the data.

    The caps matter as much as the additions. A game that can end on a
    condition is not really decided by its tally; two lines on the scorepad
    are not a salad however big the numbers on them get (Brass wins with 180
    points out of exactly two interdependent tallies); and a contested or
    minimum-of score is not an accumulation at all.
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

    # The disqualifiers. Each is a reason the tally is not what the game is
    # about, so they land near the bottom of the scale rather than at a
    # single zero: a co-op has no tally to speak of, while a money game with
    # four categories feeding it is further up than one with a single engine.
    if "coop_goal" in ends_all:
        return 0
    if shape == "objective_count":
        return _spread(2, srcs)
    if shape == "single_currency" and is_money(f) and subs <= 2:
        return _spread(4, srcs)
    if shape == "majority_control" and srcs <= 1:
        return _spread(2, srcs)
    if ends == "target_score" and score is not None and score <= RACE_SCORE:
        return _spread(3, srcs)
    if subs <= 1 and srcs <= 1:
        return 2
    if score is not None and score <= SMALL_SCORE:
        return _spread(5, srcs)

    # How big the winning total is, ramped rather than stepped, worth a bit
    # over half the scale on its own.
    if score is None:
        size = 22 if subs <= 2 else 34
    elif score < MID_SCORE:
        size = _ramp(score, SMALL_SCORE, MID_SCORE, 8, 26)
    elif score < BIG_SCORE:
        size = _ramp(score, MID_SCORE, BIG_SCORE, 26, 44)
    else:
        size = _ramp(score, BIG_SCORE, 250, 44, 55)

    breadth = {0: 0, 1: 0, 2: 8, 3: 18, 4: 26}.get(srcs, 30)
    engines = {0: 0, 1: 0, 2: 5, 3: 11}.get(subs, 15)
    total = size + breadth + engines
    if (f.get("tally") or "").strip() == "endgame":
        total += 5

    # The ceilings, in the same order the label version applied them.
    if "sudden_death" in ends_all:
        total = min(total, SALAD_BANDS[1] - 1)
    if srcs <= 2:
        total = min(total, SALAD_BANDS[1] - 1)
    elif srcs == 3:
        total = min(total, SALAD_BANDS[2] - 1)
    if shape in ("lowest_category", "majority_control"):
        total = min(total, SALAD_BANDS[2] - 1)
    return max(0, min(100, int(round(total))))


def _ramp(x, lo, hi, out_lo, out_hi):
    """x within [lo, hi] mapped onto [out_lo, out_hi], clamped."""
    if hi <= lo:
        return out_lo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return out_lo + t * (out_hi - out_lo)


def _spread(base, srcs):
    """Keep the disqualified games faintly ordered by how broad they are, so
    the column still sorts sensibly down at the bottom of the scale."""
    return min(SALAD_BANDS[0] - 1, base + min(srcs, 5))


# Where the four words sit on the 0-100 scale. Only the presentation depends
# on these, and more bands can be cut from the same number without touching
# anything that computes it.
SALAD_BANDS = (11, 40, 72)


def salad_from_score(n):
    if n is None:
        return None
    if n < SALAD_BANDS[0]:
        return "no"
    if n < SALAD_BANDS[1]:
        return "touch"
    if n < SALAD_BANDS[2]:
        return "lot"
    return "total"


def salad(f):
    """How much of a point salad, as one of SALAD_ORDER.

    Thin wrapper now: the number is the thing that is computed, and the word
    is a band cut from it. Keeping the two in one place is what makes "how
    many bands does the report show" a question about presentation only.
    """
    return salad_from_score(salad_score(f))


def _win_for(end, by, shape, fallback="", money=True, primary=False):
    """One ending, as a way of winning. `by` is what the rules say settles it;
    the score's shape stands in when a record does not say."""
    if end == "coop_goal":
        return "coop"
    if end == "elimination":
        return "elimination"
    if by == "instant" or (not by and end == "sudden_death"):
        # Winning the moment you finish something is a race when that is how
        # the game normally ends — The Quest for El Dorado's finish line — and
        # a sudden death when it is the alternative to the usual ending, like
        # Root's dominance card next to its race to thirty.
        if primary and end != "sudden_death":
            return "race"
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
    for n, (how, by) in enumerate(ends):
        w = _win_for(how, by, shape, fallback, money, primary=(n == 0))
        if w not in out:
            out.append(w)
    return out[:3]


def win(f):
    """The main way to win, for sorting and for a one-word column."""
    ws = wins(f)
    return ws[0] if ws else None
