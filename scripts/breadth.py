"""How broadly a game's victory points are spread — the "point salad" axis.

Like interaction.py this is derived, not a BGG statistic. A yes/no salad flag
was too blunt: plenty of games trend broad without being pure salads, and they
are clearly different from games where one contested currency decides
everything.

The model counts *kinds of evidence* rather than applying hand-tuned weights
per mechanic, and it contains no per-game verdicts at all. Both choices are
deliberate: a weighted table invites quietly encoding individual opinions, and
a list of named games is not a model, it is a lookup.

It rests on one measured finding. Comparing a set of broad-scoring games
against a set of focused ones, the sharpest separator by a distance was how
many *shared-pool* mechanics a game has — an auction, a market, a stock
track, a shared price (focused games averaged 1.43 of them, broad ones 0.19).
The second was whether the game supports solo play (0.62 vs 0.07), which makes
sense: a game that works alone is one where your score comes from your own
engine rather than from beating anybody. Two signals that looked plausible
turned out to be worthless and are deliberately absent — the raw count of
mechanics (gap 0.03) and BGG weight (gap 0.17).

So: score = (private-scoring signals) − 1.5 × (shared-contest signals), and the
shared side is weighted higher because it separates harder.
"""

# Evidence that score accrues privately, on your own board, from many sources.
PRIVATE_MECHANICS = {
    "End Game Bonuses", "Set Collection", "Contracts", "Tags",
    "Solo / Solitaire Game", "Tech Trees / Tech Tracks", "Track Movement",
    "Grid Coverage", "Pattern Building", "Victory Points as a Resource",
    "Automatic Resource Growth", "Layering", "Enclosure", "Income",
    "Open Drafting", "Variable Set-up",
}
PRIVATE_FAMILIES = {
    "Mechanism: Tableau Building",
    "Players: Games with Solitaire Rules",
}

# Evidence that one contested pool decides it: everyone is pulling on the same
# rope, so points cannot quietly accumulate in parallel.
SHARED_MECHANICS = {
    "Market", "Stock Holding", "Commodity Speculation", "Auction / Bidding",
    "Constrained Bidding", "Closed Economy Auction", "Selection Order Bid",
    "Turn Order: Auction", "Auction: Turn Order Until Pass",
    "Auction: Fixed Placement", "Auction: Once Around", "Auction: Dutch",
    "Auction: Sealed Bid", "Auction: Multiple Lot",
    "Area Majority / Influence", "Take That", "Multi-Use Cards", "Negotiation",
    "Player Elimination", "King of the Hill", "Highest-Lowest Scoring",
    "Trick-taking", "Betting and Bluffing", "Increase Value of Unchosen Resources",
    "Hidden Victory Points", "Score-and-Reset Game",
}
SHARED_FAMILIES = {
    "Components: Multi-Use Cards",
}

SHARED_WEIGHT = 1.5

LEVELS = ("Focused", "Some", "Broad", "Salad")
THRESHOLDS = ((5.5, "Salad"), (3.5, "Broad"), (1.5, "Some"))

# Why a game lands where it does, as multi-selectable traits. A game can carry
# traits from both sides — that is the point, and it is what a single flag
# could never express.
TRAITS = {
    "End-game bonuses": ["End Game Bonuses", "Victory Points as a Resource"],
    "Set collection": ["Set Collection", "Contracts"],
    "Multi-track": ["Tech Trees / Tech Tracks", "Track Movement", "Rondel"],
    "Parallel engine": ["Solo / Solitaire Game", "Automatic Resource Growth",
                        "Income"],
    "Tableau multipliers": ["Tags", "Layering", "Pattern Building"],
    "Contested market": ["Market", "Commodity Speculation", "Stock Holding",
                         "Increase Value of Unchosen Resources"],
    "Auction": ["Auction / Bidding", "Constrained Bidding",
                "Closed Economy Auction", "Selection Order Bid",
                "Turn Order: Auction", "Auction: Turn Order Until Pass",
                "Auction: Fixed Placement", "Auction: Once Around",
                "Auction: Dutch", "Auction: Sealed Bid", "Auction: Multiple Lot"],
    "Area control": ["Area Majority / Influence", "Enclosure", "Map Reduction"],
    "Direct conflict": ["Take That", "Player Elimination", "Negotiation",
                        "King of the Hill", "Kill Steal"],
}


def score(mechanics, families=()):
    """Private signals minus weighted shared signals. Counts, not weights."""
    m, f = set(mechanics), set(families)
    private = len(m & PRIVATE_MECHANICS) + len(f & PRIVATE_FAMILIES)
    shared = len(m & SHARED_MECHANICS) + len(f & SHARED_FAMILIES)
    return round(private - SHARED_WEIGHT * shared, 2)


def traits(mechanics):
    got = set(mechanics)
    return [name for name, tags in TRAITS.items() if got & set(tags)]


def classify(name, mechanics, families=(), overrides=None):
    """Return (level, score, traits).

    `overrides` is a user-supplied {name: level} map — breadth-overrides.txt —
    for the cases where BGG's tags genuinely cannot see what a game does. It
    ships empty on purpose: every level below is computed.
    """
    s = score(mechanics, families)
    level = "Focused"
    for cutoff, label in THRESHOLDS:
        if s >= cutoff:
            level = label
            break
    if overrides and name in overrides:
        level = overrides[name]
    return level, s, traits(mechanics)
