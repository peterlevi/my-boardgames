"""Derive a "level of interaction" rating for each game.

IMPORTANT: this is NOT a BGG statistic. BGG's XML API has no interaction
field, and neither does geekgroup's API — nothing authoritative exists to
import. This is a heuristic classifier over BGG's own mechanic and category
vocabulary, and it is the one column in the report that is opinion rather
than data. Treat it as a sorting aid.

The rule is deliberately legible rather than clever:

  1. Any mechanic or category that means players act *on* each other —
     attacking, negotiating, blocking, bluffing, talking — makes it High.
  2. Otherwise, sum the signals for competing over something *shared* — an
     auction, a majority, a worker slot, a market price. Enough of those
     make it Medium.
  3. Otherwise it is parallel play: Low.

An earlier version summed weights over every mechanic. That scored games with
long mechanic lists high regardless of content (Twilight Imperium 31, Dixit
13.5) while brutally competitive games with short euro tag lists came out Low
(Food Chain Magnate 0.5). Counting *kinds* of signal rather than quantity of
tags fixed that.
"""

# Any one of these is enough: players are directly acting on each other.
DIRECT = {
    "Negotiation", "Trading", "Bribery", "Alliances", "Voting",
    "Betting and Bluffing", "Player Elimination", "Kill Steal",
    "Traitor Game", "Hidden Roles", "King of the Hill", "Tug of War",
    "Zone of Control", "Static Capture", "Line of Sight",
    "Secret Unit Deployment", "Hidden Movement", "Area-Impulse",
    "Command Cards", "Campaign / Battle Card Driven",
    "Card Play Conflict Resolution", "Trick-taking", "Targeted Clues",
    "Communication Limits", "Cooperative Game", "Storytelling", "Singing",
}
DIRECT_CATEGORIES = {
    "Wargame", "Fighting", "Negotiation", "Political", "Party Game",
    "Bluffing", "Spies/Secret Agents",
}

# Real interaction, but routinely tagged for a variant or a single card — one
# alone means little (Cartographers is tagged "Take That" for its ambushes,
# Agricola "Team-Based Game" for a team mode). Two of them do mean something.
DIRECT_SOFT = {
    "Take That", "Team-Based Game", "Deduction", "Real-Time",
    "Roles with Asymmetric Information", "Lose a Turn", "Memory",
}
DIRECT_SOFT_MIN = 2

# Competing over a shared pool. Weighted: 1.0 signals are contested by
# construction, 0.5 signals only sometimes bite.
SHARED = {
    "Area Majority / Influence": 1.0, "Auction / Bidding": 1.0,
    "Constrained Bidding": 1.0, "Closed Economy Auction": 1.0,
    "Selection Order Bid": 1.0, "Predictive Bid": 1.0,
    "Turn Order: Auction": 1.0, "Auction: Turn Order Until Pass": 1.0,
    "Auction: Fixed Placement": 1.0, "Auction: Once Around": 1.0,
    "Auction: Dutch": 1.0, "Auction: Sealed Bid": 1.0,
    "Auction: Multiple Lot": 1.0, "Worker Placement": 1.0,
    "Worker Placement, Different Worker Types": 1.0,
    "Worker Placement with Dice Workers": 1.0, "Turn Order: Claim Action": 1.0,
    "Market": 1.0, "Commodity Speculation": 1.0, "Stock Holding": 1.0,
    "Follow": 1.0, "Increase Value of Unchosen Resources": 1.0,
    "Closed Drafting": 1.0, "Catch the Leader": 1.0, "Advantage Token": 0.5,
    "Force Commitment": 1.0, "Map Reduction": 1.0, "Neighbor Scope": 1.0,
    "Open Drafting": 0.5, "Action Drafting": 0.5, "Enclosure": 0.5,
    "Network and Route Building": 0.5, "Connections": 0.5, "Ownership": 0.5,
    "Investment": 0.5, "Pick-up and Deliver": 0.5, "Loans": 0.5,
    "Tile Placement": 0.5, "Turn Order: Pass Order": 0.5,
    "Sudden Death Ending": 0.5, "Highest-Lowest Scoring": 0.5,
    "Move Through Deck": 0.5, "Mancala": 0.5, "Slide / Push": 0.5,
}
# Tells that the players are each solving their own board. Subtracted, so a
# roll-and-write with one incidental "Take That" card still reads as parallel.
SOLITAIRE = {
    "Paper-and-Pencil": -1.0, "Bingo": -1.0, "Pattern Recognition": -0.5,
    "Simultaneous Action Selection": -0.5, "Solo / Solitaire Game": -0.25,
    "Pattern Building": -0.5, "Grid Coverage": -0.5,
}
SHARED_MIN = 1.0

# Where BGG's tags genuinely mislead. Each needs a reason, not a preference.
OVERRIDES = {
    # Tagged as a mild euro (market/worker placement), played as a knife fight:
    # every sale is taken directly off another player's board.
    "Food Chain Magnate": "High",
    # Route denial and price crashes are the whole game; the tags only say
    # "network building".
    "Indonesia": "High",
    # Stock manipulation and dumping companies on opponents.
    "1830: Railways & Robber Barons": "High",
    "1846: The Race for the Midwest": "High",
    "18Chesapeake": "High",
    # Cutthroat share pricing between players, untagged.
    "Arkwright": "High",
    "Imperial Steam": "High",
    # Attacking another player's kingdom with a war of leaders is the core of
    # the game; BGG tags it only "Area Majority / Influence".
    "Tigris & Euphrates": "High",
    # Untagged, but placement is a fight over adjacency and planet denial.
    "Gaia Project": "Medium",
    # A pure spatial puzzle everyone solves in parallel; "Race" overstates it.
    "Ricochet Robots": "Low",
}

LEVELS = ("Low", "Medium", "High")


# What *kind* of interaction, in one or two words, as against how much of it.
#
# The level answers "do the players touch each other"; this answers "how".
# It is computed, not asked for — the opinion pass already writes a sentence
# describing the mechanism ("area-majority fights over shared cities",
# "drafting from a shared display to deny colors"), and that sentence is the
# fact. Turning it into one of a dozen words is a rule you can read and argue
# with, which is the same division of labour win condition and point salad
# use: facts from the model, verdicts from code.
#
# Asking the model for the category directly was not tried and should not be:
# the prose it already returns is more specific than any label, and a second
# question would cost money to get something less precise.
#
# ORDER IS THE RULE. The first pattern that matches wins, so the list runs
# from the most particular kind of interaction to the most general. Area
# control sits above direct attacks deliberately: "area-majority fights over
# shared cities" is an area game, and putting attacks first filed every one
# of them under the word "fights".
KINDS = [
    ("Hidden roles", r"hidden[- ]role|traitor|accus|betray|hidden[- ]team|"
                     r"social deduc|who is"),
    ("Negotiation", r"negotiat|trad(e|ing)|deal[- ]making|bribe|alliance|"
                    r"\bvot(e|ing)|diplomac"),
    ("Auction", r"auction|bidding|\bbids?\b|outbid"),
    ("Area control", r"area[- ](majority|control|influence)|majorit|"
                     r"control of (the )?(town|cit|region|territor|area|province)|"
                     r"territor|contested (region|area|map)"),
    # "fight" only where it is literal. Players "fight over" a market or a
    # spot in half the euros in the collection, and reading that as combat
    # filed Brass: Birmingham — "fighting over shared coal/iron markets and
    # contested network links" — under direct attacks.
    ("Direct attacks", r"\battack|combat|battle|"
                       r"\bfight(?!(ing|s)?\s+(over|for)\b)|\bwar\b|shoot|"
                       r"damage|kill|eliminat|take[- ]that|steal|\brob\b|"
                       r"raid|invad|conquer|sabotag|destroy"),
    ("Blocking", r"block|deny|denies|denying|cut(s|ting)? off|\block\b|"
                 r"action[- ]space|worker placement|limited (action|building|"
                 r"placement) (spot|space|slot)|contested (spot|space|slot|track)"),
    ("Shared market", r"market|price|stock|shares?\b|commodit|hotel chain"),
    ("Drafting", r"draft|shared (card |tile )?(display|pool)|passing cards"),
    ("Shared actions", r"follow mechanic|piggyback|role selection|"
                       r"same role|phase selection|everyone.*your (action|role)"),
    ("Paying rivals", r"pay(ing|s)? (opponents|rivals|other players|them)|"
                      r"building fees|forces a payment|toll"),
    ("Race", r"\brac(e|ing)|before (others|rivals|opponents)|first to\b|"
             r"end the game outright"),
    ("Co-op", r"cooperat|co-op|against the game|shared goal|team"),
    ("Parallel play", r"multiplayer solitaire|little (direct )?interaction|"
                      r"minimal|almost no|no direct|parallel|indirect only"),
]

KIND_NAMES = [k for k, _ in KINDS]


def _match_kinds(text):
    """Every kind the text evidences, in KINDS order — most particular first."""
    import re
    t = (text or "").lower()
    if not t:
        return []
    return [name for name, pat in KINDS if re.search(pat, t)]


def classify_kinds(prose, mechanics=(), categories=(), level=None, limit=3):
    """The kinds of interaction a game shows, most particular first.

    A game rarely does one thing. Great Western Trail's own description —
    "paying opponents to use their buildings, and racing for limited track
    spaces" — is three kinds at once, and naming only the first throws away
    most of what it says. The order is KINDS order, so the first is the most
    particular and is what a single-line column shows.

    Read in order of how much the source actually knows: the opinion pass's
    own sentence first, then BGG's mechanic and category vocabulary for a game
    that has no opinion entry. A game whose level came out Low and matched
    nothing is parallel play by elimination — that *is* what Low means.
    """
    found = (_match_kinds(prose)
             or _match_kinds(" ".join(list(mechanics) + list(categories)))
             or (["Parallel play"] if level == "Low" else []))
    return found[:limit]


def classify_kind(prose, mechanics=(), categories=(), level=None):
    """Just the most particular kind, for a column with one line to spend."""
    found = classify_kinds(prose, mechanics, categories, level)
    return found[0] if found else None


def classify(name, mechanics, categories):
    """Return (level, shared_signal_total). See module docstring for the rule."""
    mech, cats = set(mechanics), set(categories)
    soft = DIRECT_SOFT & mech
    shared = round(sum(SHARED.get(m, 0) for m in mechanics)
                   + sum(SOLITAIRE.get(m, 0) for m in mechanics)
                   + 0.5 * len(soft), 2)
    if name in OVERRIDES:
        return OVERRIDES[name], shared
    if DIRECT & mech or DIRECT_CATEGORIES & cats or len(soft) >= DIRECT_SOFT_MIN:
        return "High", shared
    if shared >= SHARED_MIN:
        return "Medium", shared
    return "Low", shared
