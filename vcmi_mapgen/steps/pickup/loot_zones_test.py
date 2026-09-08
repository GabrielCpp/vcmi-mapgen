"""Reliability tests for steps.pickup.loot_zones's single-entrance eligibility check
and its loot-zone content restrictions."""
from vcmi_mapgen.steps.pickup import loot_zones as LZ

_BOUNDS = (64, 64)


def _zone_records(blocked_at=None):
    """Zone 0: an 8x7 (56-tile, within LOOT_ZONE_MAX_TILES=60) candidate at x0-7,y0-6.
    Zone 1: a large neighbour directly BELOW zone 0 (x0-39,y7-39), sharing one
    horizontal boundary row (y=6/y=7) -- every zone-0 tile on that row is
    zone-terrain-adjacent to a zone-1 tile, so a check blind to placed objects sees ONE
    contiguous boundary run. `blocked_at` optionally places a single-cell blocking
    object in the middle of that row, splitting it into two real passable gaps."""
    ts0 = {(x, y) for x in range(8) for y in range(7)}
    ts1 = {(x, y) for x in range(40) for y in range(7, 40)}
    zr0 = {"zid": 0, "terrain": "grass", "ts": ts0, "open_set": set(ts0),
           "passable": set(ts0), "reach": set(ts0), "used": set()}
    zr1 = {"zid": 1, "terrain": "grass", "ts": ts1, "open_set": set(ts1),
           "passable": set(ts1), "reach": set(ts1), "used": set()}
    objs_existing = []
    if blocked_at is not None:
        objs_existing.append({"x": blocked_at[0], "y": blocked_at[1], "l": 0,
                               "purpose": None, "mask": ["B"],
                               "template": {"mask": ["B"]}})
    return [zr0, zr1], objs_existing


def test_a_single_entrance_zone_qualifies_as_a_loot_zone():
    """Control: with no blocking object splitting the shared boundary, zone 0 has
    exactly one real passable gap into zone 1 and must be selected."""
    zone_records, objs_existing = _zone_records(blocked_at=None)
    objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                               seed=1, bounds=_BOUNDS)
    assert n_placed == 1
    assert zids == {0}


def test_a_vegetation_wall_splitting_the_border_disqualifies_the_zone():
    """A single blocking object in the middle of the shared boundary row splits it
    into two disjoint passable gaps -- the zone borders its neighbour through TWO
    separate openings, so it must NOT be treated as single-entrance, even though
    the raw zone-vs-zone terrain adjacency (ignoring the blocker) is still one
    contiguous run."""
    zone_records, objs_existing = _zone_records(blocked_at=(3, 6))
    objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                               seed=1, bounds=_BOUNDS)
    assert n_placed == 0
    assert zids == set()


_ALLOWED_CHEST_TYPES = {"campfire", "treasureChest", "pandoraBox", "scholar", "spellScroll"}
_ALLOWED_ART_TYPES = {"randomArtifactMajor", "randomArtifactRelic"}
_ALLOWED_RESOURCE_SUBTYPES = {"mercury", "sulfur", "crystal", "gems", "gold"}
_ALLOWED_HERO_STRUCTURE_TYPES = {
    "libraryOfEnlightenment", "arena", "marlettoTower", "hillFort", "treeOfKnowledge",
    "schoolOfMagic", "learningStone", "gardenOfRevelation", "starAxis",
}


def test_loot_zone_fill_only_uses_the_allowed_content_categories():
    """A loot zone's dense fill is artifacts of level >= 3 (major/relic), chests
    (treasure chest / campfire / pandora's box / scholar / a fixed level 4-5 spell
    scroll), one of the 9 whitelisted hero-strengthening structures (never more than
    once each), or resources other than wood/ore -- never a treasure/minor artifact,
    an unrestricted random artifact/resource, a random/unconfigured spell scroll, or
    an unrelated REWARD_PICKUP type (corpse, leanTo, wagon, ...)."""
    from vcmi_mapgen import ontology as ON

    zone_records, objs_existing = _zone_records(blocked_at=None)
    objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                               seed=1, bounds=_BOUNDS)
    assert n_placed == 1, "fixture must actually produce a loot zone to check content"

    violations = []
    hero_structure_types_seen = []
    for o in objs:
        purpose = o.get("purpose")
        typ = o.get("type")
        if typ in _ALLOWED_HERO_STRUCTURE_TYPES:
            hero_structure_types_seen.append(typ)
        elif purpose == "REWARD_PICKUP" and typ != "artifact":
            if typ == "spellScroll":
                if ON.spell_level(o.get("subtype")) not in (4, 5):
                    violations.append(o)
            elif typ not in _ALLOWED_CHEST_TYPES | _ALLOWED_ART_TYPES:
                violations.append(o)
        elif purpose == "RESOURCE_PILE":
            if o.get("subtype") not in _ALLOWED_RESOURCE_SUBTYPES:
                violations.append(o)
    assert violations == []
    assert len(hero_structure_types_seen) == len(set(hero_structure_types_seen)), (
        "no whitelisted hero-strengthening structure may be placed twice in one zone")


def test_loot_zone_fill_claims_every_non_access_tile():
    """Every tile of a sealed loot zone ends up occupied except the access object's own
    interactive cell -- an unfilled interior tile bordering water would let a boat-borne
    hero dock directly onto it, bypassing the gate/monolith entirely (user-mandated)."""
    from vcmi_mapgen.kit import objects as OR

    ts0 = _zone_records()[0][0]["ts"]
    ran_at_least_once = False
    for seed in range(1, 8):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        ran_at_least_once = True
        claimed = set()
        access_interactive = set()
        for o in objs:
            if (o["x"], o["y"]) not in ts0 and not any(
                    (cx, cy) in ts0 for cx, cy, _b in OR.mask_cells(o["mask"], o["x"], o["y"])):
                continue
            for cx, cy, _b in OR.mask_cells(o["mask"], o["x"], o["y"]):
                if (cx, cy) in ts0:
                    claimed.add((cx, cy))
            if o.get("purpose") in ("QUEST_GATE", "TRANSPORT"):
                access_interactive |= set(OR.mask_interactive_cells(o["mask"], o["x"], o["y"])) & ts0
        gap = ts0 - claimed - access_interactive
        assert not gap, f"seed {seed}: unclaimed loot-zone tiles {sorted(gap)}"
    assert ran_at_least_once, "fixture assumption broke: no seed produced a loot zone"


def test_loot_zone_fill_across_many_seeds_never_duplicates_a_hero_structure():
    """Stress the Pass-1 dedup across many seeds/zone sizes -- a single seed's small
    zone might never place enough structures to expose a duplicate-allowing bug."""
    for seed in range(1, 20):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        types = [o["type"] for o in objs if o.get("type") in _ALLOWED_HERO_STRUCTURE_TYPES]
        assert len(types) == len(set(types)), f"seed {seed}: duplicate hero structure {types}"


def test_loot_zone_fill_eventually_places_a_fixed_level_4_or_5_spell_scroll():
    """The spell-scroll chest-tier option must actually fire (not just never violate
    the rule because it never gets picked) -- sampled across enough seeds/zone sizes
    that a 1-in-5 chest-kind roll is virtually guaranteed to land at least once."""
    from vcmi_mapgen import ontology as ON

    found = None
    for seed in range(1, 40):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=_BOUNDS)
        scroll = next((o for o in objs if o.get("type") == "spellScroll"), None)
        if scroll is not None:
            found = scroll
            break
    assert found is not None, "no spell scroll appeared across 39 seeds -- check the wiring"
    assert ON.spell_level(found["subtype"]) in (4, 5)
