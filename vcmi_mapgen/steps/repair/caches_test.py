"""Reliability tests for steps.repair.caches (pocket caches, seer-hut quests, place_pickups)."""
import os

import pytest

from vcmi_mapgen.steps.vegetation import stats as PS

HAVE_STATS = os.path.exists(os.path.join(PS.PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


@needs_stats
def test_pickup_layer_legal_and_deterministic():
    from vcmi_mapgen.steps.gameplay import mines as PG
    from vcmi_mapgen.steps.gameplay.water import _legal
    from vcmi_mapgen.steps.repair import caches as CA
    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    zones = {1: {"tiles_set": sorted(ts), "centroid": (14.5, 11.5), "area": len(ts),
                 "terrain_type": 2}}
    # synthetic open field with a sealed-off pocket-ish structure: a web cross + nooks
    prot = {(x, 12) for x in range(30)} | {(15, y) for y in range(24)}
    open_set = set(ts)
    o1 = CA.place_pickups(ts, zones, 1, "grass", open_set, prot, seed=6)
    o2 = CA.place_pickups(ts, zones, 1, "grass", open_set, prot, seed=6)
    assert o1 == o2, "pickup layer must be seed-deterministic"
    assert o1, "a 720-tile grass zone should hold pickups"
    from vcmi_mapgen.kit import objects as OR
    used = set()
    for o in o1:
        if o["purpose"] == "GUARD":
            # a guard's decorative sprite-bleed cells MAY overlap terrain or already-placed
            # cache pickups (the pocket it seals is packed by design); only its interactive
            # cell — the tile the monster actually stands on — must be free and unique
            inter = OR.mask_interactive_cells(o["template"]["mask"], o["x"], o["y"])
            assert inter and used.isdisjoint(inter), "guard stand-tile must be free"
            used.update(inter)
            assert (o["x"], o["y"]) not in prot, "guards must not sit on the mandatory web"
            continue
        cells = _legal({"mask": o["template"]["mask"]}, o["x"], o["y"], open_set, set())
        assert cells is not None, "footprint must lie on open tiles"
        assert used.isdisjoint(cells), "pickups must not overlap each other"
        used.update(cells)


def _field(w, h, walls):
    return {(x, y) for x in range(w) for y in range(h)} - set(walls)


def test_find_pockets_drawn_shapes():
    """Regression fixture from the user's own drawings, updated 2026-09 for the 2-tile
    doorway model (a pocket's mouth is exactly two 4-connected tiles, replacing the
    single-guard-3x3-zone-of-control model this superseded). A flat 1-2 tile nook whose
    flanking walls do NOT protrude past its front (open diagonals on both sides) is no
    longer detectable: H3 diagonal movement gives it THREE independent entrances (front
    + both diagonals), and only 2 tiles can never block all three at once -- this is a
    real, accepted narrowing from the previous model, not a bug (see kit.topology.
    find_pockets' docstring). A nook whose flanking walls DO protrude (blocking the
    diagonals) still has only one real approach and remains detectable as a 2-tile
    doorway (entrance tile + the tile behind it, in the approach direction)."""
    from vcmi_mapgen.steps.repair import caches as CA
    from vcmi_mapgen.kit.topology import find_pockets

    def best_mouths(reach, pocket_tiles):
        """canonical (deduped, ranked) mouth candidates whose pocket covers the nook"""
        raw = {g: c for g, c in find_pockets(reach).items()
               if set(pocket_tiles) <= c[0]}
        return [cands[0][2] for cands in CA._dedupe_pockets(raw, reach)]

    # Flat 1-tile nook, open diagonals on both sides -- no longer sealable by 2 tiles.
    #     . . .
    #     X o X
    #     X X X
    reach = _field(12, 12, {(4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(5, 5)}) == []

    # Flat 2-tile nook, open diagonals -- same reason, no longer sealable.
    reach = _field(12, 12, {(3, 5), (6, 5), (3, 6), (4, 6), (5, 6), (6, 6)})
    assert best_mouths(reach, {(4, 5), (5, 5)}) == []

    # Protruding-corner nook: flanking walls block both diagonals, leaving exactly one
    # approach -- still detectable, mouth = the entrance tile + the tile behind it.
    reach = _field(12, 12, {(4, 4), (6, 4), (4, 5), (6, 5), (4, 6), (5, 6), (6, 6)})
    (mouth_fs,) = best_mouths(reach, {(5, 5)})
    assert mouth_fs == frozenset({(5, 3), (5, 4)})

    # Dead-end corridor -- 2-tile doorway at the corridor entrance, treasures behind.
    #     X X X X X X
    #     X . . . . .
    #     X X X X X X
    walls = ({(x, 5) for x in range(2, 8)} | {(2, 6)} | {(x, 7) for x in range(2, 8)})
    (mouth_fs,) = best_mouths(_field(14, 14, walls),
                              {(3, 6), (4, 6), (5, 6), (6, 6)})
    assert mouth_fs == frozenset({(7, 6), (8, 6)})

    # Bent corridor, user's `O` = guard opening, `P` = treasure tiles
    #       X X X X X X
    #     X X X P P P P O
    #     X P P P X X X X
    #     X X X X X
    walls = ({(x, 5) for x in range(5, 11)} | {(x, 6) for x in range(3, 6)} |
             {(3, 7)} | {(x, 7) for x in range(7, 11)} | {(x, 8) for x in range(3, 8)})
    P = {(6, 6), (7, 6), (8, 6), (9, 6), (4, 7), (5, 7), (6, 7)}
    (mouth_fs,) = best_mouths(_field(20, 20, walls), P)
    assert mouth_fs == frozenset({(10, 6), (11, 6)})

    # control: a lone straight wall through an open field must yield no pocket anywhere,
    # including its two ends against the map edge (no 2-tile doorway sealing them either).
    reach = _field(12, 12, {(x, 6) for x in range(12)})
    assert find_pockets(reach) == {}


@needs_stats
def test_scatter_rewards_are_mostly_loot():
    """Unguarded reward scatter favours the fixed LOOT pool (treasure chests dominate the
    corpus mix) over random artifacts, and a real zone always yields some loot."""
    from vcmi_mapgen.steps.gameplay import mines as PG
    from vcmi_mapgen.steps.repair import caches as CA
    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    zones = {1: {"tiles_set": sorted(ts), "centroid": (14.5, 11.5), "area": len(ts),
                 "terrain_type": 2}}
    prot = {(x, 12) for x in range(30)} | {(15, y) for y in range(24)}
    rewards = []
    for seed in range(1, 10):
        objs = CA.place_pickups(ts, zones, 1, "grass", set(ts), prot, seed=seed)
        rewards += [o for o in objs if o["purpose"] == "REWARD_PICKUP"]
    assert rewards, "a 720-tile zone (>= LOOT_FLOOR_AREA) must yield reward pickups"
    # guarded-pocket rewards are deliberately tiered random artifacts (bug-report fix: those
    # pockets were underutilized); the LOOT-pool claim applies to the unguarded scatter only
    scatter_rewards = [o for o in rewards if not o.get("cache")]
    loot = [o for o in scatter_rewards if "random" not in str(o["type"]).lower()]
    assert any(o["type"] == "treasureChest" for o in loot), \
        "treasure chests must appear as unguarded loot"
    assert len(loot) >= len(scatter_rewards) * 0.5, \
        f"scatter must be mostly fixed loot, got {len(loot)}/{len(scatter_rewards)}"


def _field_with_room(room, mouth, field_w=15, field_h=4):
    field = {(x, y) for x in range(field_w) for y in range(field_h)}
    ts = field | set(mouth) | set(room)
    return {"zid": 0, "terrain": "grass", "ts": ts, "open_set": set(ts),
            "passable": set(ts), "reach": set(ts), "used": set()}


@needs_stats
def test_pocket_guard_level_matches_artifact_tier_exactly():
    """Level of the guard monster == level of the artifact at the deep end (user-mandated
    2026-09) -- no random +1 bump on the guard, unlike the pre-redefinition behavior."""
    import re
    from vcmi_mapgen.steps.gameplay import mines as PG
    from vcmi_mapgen.steps.repair import caches as CA
    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}   # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    objs, n_pockets, _depth = CA.place_pocket_caches([zr], seed=3, bounds=(20, 20))
    assert n_pockets == 1, "fixture assumption broke: expected exactly one pocket"
    guard = next(o for o in objs if o.get("purpose") == "GUARD")
    art = next(o for o in objs if o.get("purpose") == "REWARD_PICKUP"
              and "artifact" in str(o.get("type", "")).lower())
    glvl = int(re.match(r"randomMonsterLevel(\d)", guard["type"]).group(1))
    assert art["animation"].lower() == CA._ART_BY_LVL[glvl - 1], (
        f"guard is level {glvl} but artifact animation {art['animation']!r} doesn't "
        f"match that tier ({CA._ART_BY_LVL[glvl - 1]!r})")


@needs_stats
def test_pocket_overlay_depth_is_only_recorded_for_pockets_that_actually_get_filled():
    """Bug (2026-09, 'not all magenta pocket tiles are filled'): `pocket_depth_by_tile`
    -- the map PocketOverlay renders straight from -- used to be written before the
    late gates that can still `continue` out of a candidate (every pocket tile already
    claimed by an earlier pass, so `cache_spots` ends up empty; or no guard fits). A
    pocket that fails one of those gates got zero objects placed on it, yet every one
    of its tiles was still recorded as pocket depth -- painted magenta with nothing
    underneath. Fixture: pre-claim every room tile as already `used` (simulating an
    earlier pass having spent it), so the accepted-candidate gates find no cache spots
    left and the whole pocket must be dropped, both from `objs` and from `depth`."""
    from vcmi_mapgen.steps.repair import caches as CA

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}   # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    zr["used"] |= room
    objs, n_pockets, depth = CA.place_pocket_caches([zr], seed=3, bounds=(20, 20))
    assert not any(o.get("purpose") == "GUARD" for o in objs)
    assert not depth, f"pocket tiles marked magenta with nothing placed: {sorted(depth)}"


@needs_stats
def test_pocket_overlay_never_marks_an_approach_reserved_tile_that_cant_receive_a_cache():
    """Same class of bug as above, at single-tile granularity (real seed-7 repro,
    2026-09: a pocket's deepest tile sat right against an existing STAT_PERMANENT
    structure's approach cell). `cache_spots`/`avail` were selected against
    `global_reach8` (physically walkable), but the actual placement calls gate on the
    STRICTER `global_place` (`global_reach8 & global_open`) -- so a pocket tile that is
    walkable but reserved as another object's approach cell (excluded from open_set)
    was always destined to fail placement, yet still got recorded as pocket depth."""
    from vcmi_mapgen.steps.repair import caches as CA
    from vcmi_mapgen.kit import objects as OR

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}   # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    zr["open_set"].discard((6, 7))     # walkable (still in ts/passable/reach) but
                                        # reserved -- e.g. another object's approach cell
    objs, n_pockets, depth = CA.place_pocket_caches([zr], seed=3, bounds=(20, 20))
    claimed = set()
    for o in objs:
        for cx, cy, _b in OR.mask_cells(o["mask"], o["x"], o["y"]):
            claimed.add((cx, cy))
    unfilled = set(depth) - claimed
    assert not unfilled, f"pocket tiles marked magenta with nothing placed: {unfilled}"


def test_pocket_guard_never_cuts_a_town_off_from_its_own_starting_mine():
    """s2-z1 diagnosis (2026-09): a pocket declared right by the castle got guarded,
    and that guard's zone-of-control (its interactive cell + all 8 neighbours -- in
    H3, standing next to a wandering monster forces combat) happened to seal the
    ONLY isthmus connecting the town to its own force_town sawmill, even though the
    sawmill already carries its own dedicated level-1 guard. Fixture: two open rooms
    joined by a single 3-tile isthmus (6,4)-(8,4), with a legitimate 1-tile pocket
    (mouth (7,3)/(7,4)) whose only guardable candidate sits AT (7,4), squarely on the
    isthmus. TOWN is in the left room, a sawmill MINE in the right room."""
    from vcmi_mapgen.steps.repair import caches as CA
    from vcmi_mapgen.kit import objects as OR

    left = {(x, y) for x in range(6) for y in range(9)}
    right = {(x, y) for x in range(9, 15) for y in range(9)}
    isthmus = {(6, 4), (7, 4), (8, 4)}
    room = {(7, 2)}
    mouth_extra = {(7, 3)}
    ts = left | right | isthmus | room | mouth_extra

    town = {"x": 2, "y": 2, "l": 0, "purpose": "TOWN", "type": "randomTown",
           "subtype": "object", "mask": ["A"], "template": {"mask": ["A"]}}
    mine = {"x": 12, "y": 2, "l": 0, "purpose": "MINE", "type": "mine",
           "subtype": "sawmill", "mask": ["A"], "template": {"mask": ["A"]}}
    zr = {"zid": 0, "terrain": "grass", "ts": ts, "open_set": set(ts),
         "passable": set(ts), "reach": set(ts), "used": set()}

    objs, n_pockets, depth = CA.place_pocket_caches(
        [zr], seed=3, bounds=(20, 20), existing_objs=[town, mine], home_zids={0})

    NB8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    guard_zoc = set()
    for o in objs:
        if o.get("purpose") != "GUARD":
            continue
        for ix, iy in OR.mask_interactive_cells(o["mask"], o["x"], o["y"]):
            guard_zoc.add((ix, iy))
            for dx, dy in NB8:
                guard_zoc.add((ix + dx, iy + dy))
    assert not (guard_zoc & isthmus), (
        f"a new pocket guard's ZoC {guard_zoc} still crosses the isthmus {isthmus} -- "
        "town cut off from its own starting mine")


@needs_stats
def test_pocket_chest_fill_uses_only_the_allowed_types():
    """The cavity's non-artifact/non-resource fill is entirely chests/pandora's box
    (treasureChest, campfire, pandoraBox) -- never scholar/corpse/spellScroll/leanTo/
    wagon/warriorTomb/denOfThieves, which "everything but an artifact" used to allow."""
    from vcmi_mapgen.steps.gameplay import mines as PG
    from vcmi_mapgen.steps.repair import caches as CA
    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")

    allowed = {"treasureChest", "campfire", "pandoraBox"}
    violations = []
    for seed in range(1, 15):
        room = {(x, y) for x in range(5, 7) for y in range(5, 10)}   # 10-tile cavity
        zr = _field_with_room(room, {(5, 4), (6, 4)})
        objs, n_pockets, _depth = CA.place_pocket_caches([zr], seed=seed, bounds=(20, 20))
        for o in objs:
            if (o.get("purpose") == "REWARD_PICKUP"
                    and "artifact" not in str(o.get("type", "")).lower()):
                if o.get("type") not in allowed:
                    violations.append(o)
    assert violations == []
