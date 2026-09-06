"""Reliability tests for steps.pickup.loot_zones's single-entrance eligibility check
and its loot-zone content restrictions."""
from vcmi_mapgen.steps.pickup import loot_zones as LZ

_BOUNDS = (64, 64)


def _zone_records(blocked_at=None):
    """Zone 0: an 8x8 candidate at x0-7,y0-7. Zone 1: a large neighbour directly
    BELOW zone 0 (x0-39,y8-39), sharing one horizontal boundary row (y=7/y=8) --
    every zone-0 tile on that row is zone-terrain-adjacent to a zone-1 tile, so a
    check blind to placed objects sees ONE contiguous boundary run. `blocked_at`
    optionally places a single-cell blocking object in the middle of that row,
    splitting it into two real passable gaps."""
    ts0 = {(x, y) for x in range(8) for y in range(8)}
    ts1 = {(x, y) for x in range(40) for y in range(8, 40)}
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
    zone_records, objs_existing = _zone_records(blocked_at=(3, 7))
    objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                               seed=1, bounds=_BOUNDS)
    assert n_placed == 0
    assert zids == set()


_ALLOWED_CHEST_TYPES = {"campfire", "treasureChest", "pandoraBox"}
_ALLOWED_ART_TYPES = {"randomArtifactMajor", "randomArtifactRelic"}
_ALLOWED_RESOURCE_SUBTYPES = {"mercury", "sulfur", "crystal", "gems", "gold"}


def test_loot_zone_fill_only_uses_the_allowed_content_categories():
    """A loot zone's dense fill is artifacts of level >= 3 (major/relic), chests
    (treasure chest / campfire / pandora's box), hero-strengthening structures, or
    resources other than wood/ore -- never a treasure/minor artifact, an
    unrestricted random artifact/resource, or an unrelated REWARD_PICKUP type
    (scholar, corpse, spell scroll, ...)."""
    zone_records, objs_existing = _zone_records(blocked_at=None)
    objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                               seed=1, bounds=_BOUNDS)
    assert n_placed == 1, "fixture must actually produce a loot zone to check content"

    violations = []
    for o in objs:
        purpose = o.get("purpose")
        if purpose == "REWARD_PICKUP" and o.get("type") != "artifact":
            if o.get("type") not in _ALLOWED_CHEST_TYPES | _ALLOWED_ART_TYPES:
                violations.append(o)
        elif purpose == "RESOURCE_PILE":
            if o.get("subtype") not in _ALLOWED_RESOURCE_SUBTYPES:
                violations.append(o)
    assert violations == []
