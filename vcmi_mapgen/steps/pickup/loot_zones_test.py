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
_ALLOWED_HERO_STRUCTURE_TYPES = {"learningStone", "gardenOfRevelation", "starAxis"}


def test_loot_zone_fill_only_uses_the_allowed_content_categories():
    """A loot zone's dense fill is artifacts of level >= 3 (major/relic), chests
    (treasure chest / campfire / pandora's box / scholar / a fixed level 4-5 spell
    scroll), the 3 whitelisted hero-strengthening structures (at most TWO of each,
    user-mandated 2026-09), or resources other than wood/ore -- never a treasure/minor
    artifact, an unrestricted random artifact/resource, a random/unconfigured spell
    scroll, or an unrelated REWARD_PICKUP type (corpse, leanTo, wagon, ...)."""
    from vcmi_mapgen import ontology as ON
    import collections

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
    counts = collections.Counter(hero_structure_types_seen)
    assert all(n <= 2 for n in counts.values()), (
        f"no whitelisted hero-strengthening structure may be placed more than twice: {counts}")


def test_loot_zone_fill_claims_every_non_access_tile():
    """Every tile of a sealed loot zone ends up occupied except the access object's own
    interactive cell -- an unfilled interior tile bordering water would let a boat-borne
    hero dock directly onto it, bypassing the gate/monolith entirely (user-mandated).
    The doorway/corridor tiles excavated for guaranteed access are NOT exempt (s7-z4
    third occurrence, 2026-09: they used to be reserved as a permanently-empty hallway,
    leaving several genuinely reachable tiles right behind the gate unfilled forever)
    -- loot fill places walk-on ('A'-mask) objects, so a resource pile or structure
    sitting in the corridor never blocks the hero's path through it. Asserts ZERO gap
    tiles."""
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


def test_loot_zone_fill_claims_every_tile_of_a_multi_tile_corridor():
    """s7-z4 third occurrence (2026-09): the corridor connecting the gate to the rest
    of the zone's room (a narrow zone shape puts more than one tile between the
    entrance and the room -- see `_narrow_zone_records`) must ALSO get filled with
    loot, not left as a permanently-reserved empty hallway. Direct regression for the
    reported symptom ('5 tiles just below the gate are not filled')."""
    from vcmi_mapgen.kit import objects as OR

    ts0 = _narrow_zone_records()[0][0]["ts"]
    ran_at_least_once = False
    for seed in range(1, 30):
        zone_records, objs_existing = _narrow_zone_records()
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=(32, 14))
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


def test_loot_zone_fill_across_many_seeds_never_exceeds_two_per_hero_structure():
    """Stress the Pass-1 per-type cap across many seeds/zone sizes -- a single seed's
    small zone might never place enough structures to expose a triplicate-allowing
    bug. Exactly two of each type is the target (user-mandated 2026-09); tile
    contention may leave fewer, but never more."""
    import collections

    for seed in range(1, 20):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        types = [o["type"] for o in objs if o.get("type") in _ALLOWED_HERO_STRUCTURE_TYPES]
        counts = collections.Counter(types)
        assert all(n <= 2 for n in counts.values()), (
            f"seed {seed}: a hero structure was placed more than twice: {counts}")


def test_loot_zone_fill_places_two_instances_of_each_hero_structure_apart_from_each_other():
    """Pass 1 (user-mandated 2026-09): TWO instances of each of the 3 whitelisted
    hero-strengthening structures, separated from one another (never adjacent/
    touching) rather than clustered together. Sampled across enough seeds/zone sizes
    that a comfortably-sized zone actually reaches the target count of 2 for at least
    one seed."""
    import collections

    _DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    saw_two_of_a_type = False
    for seed in range(1, 20):
        zone_records, objs_existing = _rect_zone_records(5, 4)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=(64, 64))
        if n_placed != 1:
            continue
        by_type = collections.defaultdict(list)
        for o in objs:
            if o.get("type") in _ALLOWED_HERO_STRUCTURE_TYPES:
                by_type[o["type"]].append((o["x"], o["y"]))
        for typ, positions in by_type.items():
            assert len(positions) <= 2, f"seed {seed}: {typ} placed {len(positions)} times"
            if len(positions) == 2:
                saw_two_of_a_type = True
                p1, p2 = positions
                assert max(abs(p1[0] - p2[0]), abs(p1[1] - p2[1])) >= LZ._LOOT_HERO_STRUCTURE_MIN_SEP, (
                    f"seed {seed}: the two {typ} instances {positions} are too close together")
    assert saw_two_of_a_type, "fixture assumption broke: no seed placed 2 of any hero structure"


def _rect_zone_records(w, h):
    """A w×h rectangular zone (zid 0) with a single boundary along its bottom edge to a
    large neighbour (zid 1) -- a plain single-entrance loot-zone fixture. Sized 5x4 (20
    tiles) it makes the old 30%-of-free-tiles cap bind: far more than 5 tiles stay free
    after sealing/access overhead, but the cap stopped hero-structure placement at 3 of
    the 5 whitelisted types."""
    ts0 = {(x, y) for x in range(w) for y in range(h)}
    ts1 = {(x, y) for x in range(40) for y in range(h, h + 30)}
    zr0 = {"zid": 0, "terrain": "grass", "ts": ts0, "open_set": set(ts0),
           "passable": set(ts0), "reach": set(ts0), "used": set()}
    zr1 = {"zid": 1, "terrain": "grass", "ts": ts1, "open_set": set(ts1),
           "passable": set(ts1), "reach": set(ts1), "used": set()}
    return [zr0, zr1], []


def test_loot_zone_fill_places_every_whitelisted_hero_structure_tile_budget_permitting():
    """Pass 1 (user-mandated 2026-09): no throttle to a fraction of the zone -- every
    whitelisted type gets its (up to two) instances placed, tile availability
    permitting. A comfortably-sized zone must see all 3 whitelisted types appear on at
    least one seed."""
    counts = []
    for seed in range(1, 20):
        zone_records, objs_existing = _rect_zone_records(5, 4)
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=(64, 64))
        if n_placed != 1:
            continue
        types = {o["type"] for o in objs if o.get("type") in _ALLOWED_HERO_STRUCTURE_TYPES}
        counts.append(len(types))
    assert counts, "fixture assumption broke: no seed produced a loot zone"
    assert max(counts) == len(_ALLOWED_HERO_STRUCTURE_TYPES), (
        f"tile budget should allow all {len(_ALLOWED_HERO_STRUCTURE_TYPES)} types on "
        f"at least one seed: {counts}")


def test_loot_zone_fill_pass2_uses_the_20_40_40_split():
    """Pass 2 (user-mandated 2026-09): 20% major/relic artifact, 40% chest, 40% rare
    resource -- not the old 30/30/40 split. Statistical check over many seeds/tiles:
    the artifact share must sit near 20%, not 30%."""
    n_art = n_chest = n_res = 0
    for seed in range(1, 60):
        zone_records, objs_existing = _zone_records()
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        ts0 = zone_records[0]["ts"]
        for o in objs:
            if (o["x"], o["y"]) not in ts0:
                continue
            typ = o.get("type")
            if typ in _ALLOWED_HERO_STRUCTURE_TYPES:
                continue
            if typ in _ALLOWED_ART_TYPES:
                n_art += 1
            elif typ in _ALLOWED_CHEST_TYPES:
                n_chest += 1
            elif o.get("purpose") == "RESOURCE_PILE":
                n_res += 1
    total = n_art + n_chest + n_res
    assert total > 500, "fixture too small to be statistically meaningful"
    art_frac = n_art / total
    assert 0.12 <= art_frac <= 0.28, (
        f"artifact share {art_frac:.2f} not near 20% (n_art={n_art}, total={total})")


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


def _narrow_zone_records():
    """A 2-wide corridor (zone 0, 12 tiles) walled by a big exterior zone (zone 1) on
    both long sides and the far end -- every zone-0 tile counts as zone perimeter, the
    exact shape that exposed the s7-z4 defect: `_seal_all_passages` seals the FULL
    perimeter (not just the single passage cluster the eligibility check found), so an
    access object's interior-side neighbor could get sealed shut even though the old
    check (which only looked at that stale passage cluster) believed it stayed open."""
    ts0 = {(x, y) for x in (2, 3) for y in range(0, 6)}
    # zone1 must NOT itself qualify as a loot zone (over LOOT_ZONE_MAX_TILES=60), or it
    # would compete with zone0 for the only slot in ext_pool, leaving no zone free to
    # host the keymaster/exterior monolith.
    ts1 = ({(1, y) for y in range(0, 6)} | {(4, y) for y in range(0, 6)}
           | {(x, y) for x in range(0, 30) for y in range(6, 12)})
    zr0 = {"zid": 0, "terrain": "grass", "ts": ts0, "open_set": set(ts0),
           "passable": set(ts0), "reach": set(ts0), "used": set()}
    zr1 = {"zid": 1, "terrain": "grass", "ts": ts1, "open_set": set(ts1),
           "passable": set(ts1), "reach": set(ts1), "used": set()}
    return [zr0, zr1], []


def test_entry_corridor_reaches_the_whole_room_not_just_the_first_doorway_tile():
    """s7-z4 second occurrence (2026-09): real seed-7 repro had a 1-tile vestibule
    (the doorway `_find_entry_tile` finds) separated from the zone's actual room by a
    FURTHER neck row that is entirely boundary-classified (adjacent to tiles outside
    the zone), because the vestibule above it is narrower than the room below. Sealing
    every boundary tile except that single vestibule tile leaves the whole room --
    every tile `_fill_loot` is meant to use -- unreachable from the gate. Direct unit
    test of `_find_entry_corridor` (the module-level fix), with a hand-built ts/all_ts
    that reproduces the exact narrow-vestibule/wide-room shape from the real map,
    bypassing `place_loot_zones`'s own gate-siting heuristics entirely."""
    import collections
    from vcmi_mapgen.steps.pickup import loot_zones as LZ

    entryrow = {(5, 0)}                                   # 1-tile vestibule (doorway)
    neck = {(x, 1) for x in range(1, 10)}                 # full-width neck row
    room = {(x, y) for x in range(1, 10) for y in range(2, 6)}
    ts = entryrow | neck | room
    box = {(x, y) for x in range(0, 11) for y in range(-1, 7)}
    all_ts = ts | (box - ts)
    entry_tile = (5, 0)

    DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    ext_ts = all_ts - ts
    boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in DIRS8)}
    interior = ts - boundary
    assert interior, "fixture assumption broke: no interior tiles to protect"

    def _reachable(skip_cells):
        avail = ts - (boundary - skip_cells)
        seen = {entry_tile} if entry_tile in avail else set()
        q = collections.deque(seen)
        while q:
            x, y = q.popleft()
            for dx, dy in DIRS8:
                nb = (x + dx, y + dy)
                if nb in avail and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        return seen

    # Old behaviour (a single reserved entry_tile) leaves the whole room unreachable.
    old_reach = _reachable({entry_tile})
    assert interior - old_reach, (
        "fixture assumption broke: single entry_tile already reaches the room "
        "-- this shape no longer reproduces the s7-z4 second occurrence")

    corridor = LZ._find_entry_corridor(entry_tile, [], ts, all_ts)
    new_reach = _reachable(corridor)
    assert interior <= new_reach, (
        f"corridor {sorted(corridor)} still leaves "
        f"{sorted(interior - new_reach)} of the room unreachable from the gate")


def test_a_narrow_loot_zones_access_object_always_has_a_usable_interior_doorway():
    """s7-z4 (2026-09): a narrow zone's interior can be entirely on the raw zone
    perimeter, which _seal_all_passages seals in full. Without a reserved doorway, the
    access object's interactive cell ends up with no passable interior neighbor at all
    -- the gate/monolith opens onto a wall. Sampled across enough seeds to exercise
    both the gate and the two-way-monolith branch (50/50 per zone)."""
    from vcmi_mapgen.kit import objects as OR

    seen_gate = seen_mono = False
    for seed in range(1, 30):
        zone_records, objs_existing = _narrow_zone_records()
        objs, n_placed, zids = LZ.place_loot_zones(zone_records, {}, objs_existing,
                                                   seed=seed, bounds=(32, 14))
        if n_placed != 1:
            continue
        access = next(o for o in objs if o.get("purpose") in ("QUEST_GATE", "TRANSPORT"))
        seen_gate = seen_gate or access["purpose"] == "QUEST_GATE"
        seen_mono = seen_mono or access["purpose"] == "TRANSPORT"
        interactive = OR.mask_interactive_cells(access["mask"], access["x"], access["y"])
        blocked = set()
        for o in objs:
            for cx, cy, blk in OR.mask_cells(o["mask"], o["x"], o["y"]):
                if blk:
                    blocked.add((cx, cy))
        ts0 = zone_records[0]["ts"]
        has_open_interior_neighbor = any(
            (ix + dx, iy + dy) in ts0 and (ix + dx, iy + dy) not in blocked
            for ix, iy in interactive
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)]
        )
        assert has_open_interior_neighbor, (
            f"seed {seed}: {access['purpose']} at ({access['x']},{access['y']}) has no "
            "passable interior neighbor -- unreachable loot zone")
    assert seen_gate, "fixture assumption broke: no seed produced a gate"
    assert seen_mono, "fixture assumption broke: no seed produced a monolith"
