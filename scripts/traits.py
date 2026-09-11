"""Derived "trait" tags: named groupings of BGG mechanics.

These are shortcuts, not judgments. Each one is simply "this game has at least
one of these mechanics", so a trait is always checkable against the tag list
rather than being an opinion about how a game plays. They earn their place
because BGG's vocabulary is granular — eleven separate auction mechanics — and
you usually want the family, not the variant.

(An earlier attempt used these to compute a single "scoring breadth" score.
That failed: it called Food Chain Magnate broad, and more than half the
collection focused. The groupings survive; the scale does not.)
"""

TRAITS = {
    "End-game bonuses": ["End Game Bonuses", "Victory Points as a Resource"],
    "Set collection": ["Set Collection", "Contracts"],
    "Multi-track": ["Tech Trees / Tech Tracks", "Track Movement", "Rondel"],
    "Parallel engine": ["Solo / Solitaire Game", "Automatic Resource Growth",
                        "Income"],
    "Tableau multipliers": ["Tags", "Layering", "Pattern Building"],
    "Contested market": ["Market", "Commodity Speculation", "Stock Holding",
                         "Increase Value of Unchosen Resources"],
    "Auction of any kind": [
        "Auction / Bidding", "Constrained Bidding", "Closed Economy Auction",
        "Selection Order Bid", "Turn Order: Auction",
        "Auction: Turn Order Until Pass", "Auction: Fixed Placement",
        "Auction: Once Around", "Auction: Dutch", "Auction: Sealed Bid",
        "Auction: Multiple Lot", "Predictive Bid"],
    "Area control": ["Area Majority / Influence", "Enclosure", "Map Reduction"],
    "Direct conflict": ["Take That", "Player Elimination", "Negotiation",
                        "King of the Hill", "Kill Steal", "Stealing"],
    "Worker placement of any kind": [
        "Worker Placement", "Worker Placement, Different Worker Types",
        "Worker Placement with Dice Workers"],
    "Deck or bag building": ["Deck, Bag, and Pool Building",
                             "Deck Construction"],
    "Drafting of any kind": ["Open Drafting", "Closed Drafting",
                             "Action Drafting", "Dice Drafting"],
    "Hidden information": ["Hidden Victory Points", "Secret Unit Deployment",
                           "Hidden Movement", "Hidden Roles",
                           "Roles with Asymmetric Information"],
    "Co-operative": ["Cooperative Game", "Semi-Cooperative Game",
                     "Team-Based Game"],
    "Network building": ["Network and Route Building", "Connections",
                         "Pick-up and Deliver"],
}

DESCRIPTIONS = {
    "End-game bonuses": "Points handed out for various things once play ends.",
    "Set collection": "Points for gathering matching or complementary things.",
    "Multi-track": "Progress is measured along one or more tracks.",
    "Parallel engine": "You build a private engine that ticks over on its own.",
    "Tableau multipliers": "Cards in front of you multiply each other's value.",
    "Contested market": "A shared market or price everyone's decisions move.",
    "Auction of any kind": "Any of BGG's eleven auction and bidding mechanics.",
    "Area control": "Holding or surrounding space on the board pays.",
    "Direct conflict": "Players can act against each other directly.",
    "Worker placement of any kind": "Placing limited workers on action spaces.",
    "Deck or bag building": "You shape the deck or bag you draw from.",
    "Drafting of any kind": "Picking from a shared, shrinking pool.",
    "Hidden information": "Something material is concealed from other players.",
    "Co-operative": "Players work together rather than against each other.",
    "Network building": "Linking places into a connected network.",
}


def of(mechanics):
    got = set(mechanics)
    return [name for name, tags in TRAITS.items() if got & set(tags)]
