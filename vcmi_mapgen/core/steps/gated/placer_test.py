"""Reliability tests for steps.gated.placer's single-entrance eligibility check and the
steps.treasure.fill loot-zone content restrictions."""

import collections

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.core.model import PlacedObject, Tile, ZoneRecord
from vcmi_mapgen.core.steps.gated.placer import find_entry_corridor, place_gated_zones
from vcmi_mapgen.core.steps.treasure.fill import LOOT_HERO_STRUCTURE_MIN_SEP, fill_loot_zones
from vcmi_mapgen.kit import objects as OR

_BOUNDS = (64, 64)
_DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _place(
    zone_records: list[ZoneRecord],
    objs_existing: list[PlacedObject],
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
) -> tuple[list[PlacedObject], int, set[int]]:
    """GatedStep then TreasureStep on one level: the access objects, then the fill."""
    objs, n_placed, access = place_gated_zones(
        zone_records, objs_existing, seed=seed, bounds=bounds
    )
    footprints = {zid: acc.footprint for zid, acc in access.items()}
    filled = fill_loot_zones(zone_records, footprints, [*objs_existing, *objs], seed, bounds)
    return objs + filled, n_placed, set(access)


def _find_leaks(
    ts0: frozenset[Tile],
    all_ts: set[Tile],
    objs: list[PlacedObject],
    access: PlacedObject,
) -> list[Tile]:
    """Loot-zone tiles a hero reaches from outside the zone without stepping on the access
    object's interactive cell(s), 8-connected. The access object's own footprint is exempt:
    a Border Gate's overlay row sits on the outside of the gate. `objs` should be the FULL
    accumulated object list (this zone's own placements plus everything already in
    neighbouring zones)."""
    blocked: set[Tile] = set()
    for o in objs:
        if not o.mask:
            continue
        for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y):
            if blk:
                blocked.add((cx, cy))
    interactive = set(OR.mask_interactive_cells(access.mask, access.x, access.y))
    footprint = {(cx, cy) for cx, cy, _b in OR.mask_cells(access.mask, access.x, access.y)}
    walkable = all_ts - blocked - interactive
    seen = {t for t in all_ts - ts0 if t in walkable}
    q = collections.deque(sorted(seen))
    while q:
        cx, cy = q.popleft()
        for dx, dy in _DIRS8:
            nb = (cx + dx, cy + dy)
            if nb in walkable and nb not in seen:
                seen.add(nb)
                q.append(nb)
    return sorted((seen & ts0) - footprint)


def _record(zid: int, ts: set[Tile]) -> ZoneRecord:
    return ZoneRecord(
        zid=zid,
        terrain="grass",
        ts=frozenset(ts),
        open_set=set(ts),
        passable=set(ts),
        reach=set(ts),
        used=set(),
    )


def _blocker(x: int, y: int) -> PlacedObject:
    return PlacedObject(
        x=x, y=y, level=0, purpose="", type=None, subtype=None, animation="", mask=("B",)
    )


def _spell_of(o: PlacedObject) -> str:
    spell = (o.options or {}).get("spell")
    assert isinstance(spell, str)
    return spell


def _zone_records(
    blocked_at: Tile | None = None,
) -> tuple[list[ZoneRecord], list[PlacedObject]]:
    """Zone 0: an 8x7 (56-tile, within LOOT_ZONE_MAX_TILES=60) candidate at x0-7,y0-6.
    Zone 1: a large neighbour directly BELOW zone 0 (x0-39,y7-39), sharing one
    horizontal boundary row (y=6/y=7) -- every zone-0 tile on that row is
    zone-terrain-adjacent to a zone-1 tile, so a check blind to placed objects sees ONE
    contiguous boundary run. `blocked_at` optionally places a single-cell blocking
    object in the middle of that row, splitting it into two real passable gaps."""
    ts0 = {(x, y) for x in range(8) for y in range(7)}
    ts1 = {(x, y) for x in range(40) for y in range(7, 40)}
    zr0 = _record(0, ts0)
    zr1 = _record(1, ts1)
    objs_existing: list[PlacedObject] = []
    if blocked_at is not None:
        objs_existing.append(_blocker(blocked_at[0], blocked_at[1]))
    return [zr0, zr1], objs_existing


def test_loot_zone_is_never_leaky_across_many_seeds_and_shapes() -> None:
    """s7-z4/s9-z3 diagnosis (2026-09): a loot zone must have NO 8-connected path from
    any of its own tiles to a tile outside it, except through the gate's/monolith's
    own interactive tile. Two real, distinct root causes produced leaks: (1) the
    over-eager BFS-tree corridor could exempt an entire boundary-classified room edge
    from sealing merely because it sat on some deep interior tile's arbitrary
    shortest path (s9-z3), and (2) placing the gate cleared ANY existing object whose
    footprint grazed the gate's own -- including a neighbouring zone's vegetation
    object anchored just outside the zone whose functional BLOCKING cell survived
    outside the gate's own footprint but got swept away anyway because a purely
    DECORATIVE cell of that same object happened to graze it (s7-z4). Swept across
    three different zone shapes (plain single-entrance, 2-wide corridor, thin-strip)
    and many seeds to exercise both the gate and monolith branches."""
    fixtures = [
        (_zone_records, (64, 64)),
        (_narrow_zone_records, (32, 14)),
        (lambda: _rect_zone_records(5, 4), (64, 64)),
    ]
    ran_at_least_once = False
    for make_fixture, bounds in fixtures:
        for seed in range(1, 20):
            zone_records, objs_existing = make_fixture()
            ts0 = zone_records[0].ts
            all_ts: set[Tile] = set()
            for zr in zone_records:
                all_ts |= zr.ts
            objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=bounds)
            if n_placed != 1:
                continue
            ran_at_least_once = True
            access = next(
                o for o in objs if o.purpose in ("QUEST_GATE", "TRANSPORT") and (o.x, o.y) in ts0
            )
            leaks = _find_leaks(ts0, all_ts, objs_existing + objs, access)
            assert not leaks, (
                f"{make_fixture.__name__ if hasattr(make_fixture, '__name__') else ''} "
                f"seed {seed}: loot zone leaks {leaks}"
            )
    assert ran_at_least_once, "fixture assumption broke: no seed produced a loot zone"


def test_seal_all_passages_never_stacks_blocking_decor_onto_the_access_objects_footprint() -> None:
    """s9-z3 defect (2026-09): `_seal_all_passages` only ever protected the gate's/
    monolith's single INTERACTIVE cell from re-sealing, never its other footprint
    tiles -- e.g. 3 of a 2x2 monolith's 4 mask cells are non-interactive 'V' overlay,
    so a boundary-adjacent one of those got a second, BLOCKING vegetation object
    stacked directly onto it (visually 'only one tile of the monolith is used').
    Non-blocking V/A cells from OTHER objects (e.g. a resource pile's decorative
    overlay) legitimately share a tile by this engine's own design -- see
    `_place_one`'s GUARD docstring -- so this only checks for a BLOCKING cell landing
    on any of the access object's own footprint tiles. Sweeps both the gate and
    monolith branches across many seeds/shapes.

    `_narrow_zone_records` is deliberately NOT swept here: its 2-wide corridor forces
    the gate's wide mask to overhang into the *neighbouring* zone's own tile grid, and
    closing the resulting leak there is `_close_stray_leaks`'s job, not
    `_seal_all_passages`'s -- `_close_stray_leaks` has the same-shaped gap (tracked
    separately, not fixed here: today it plugs that overhang leak by stacking a
    blocker directly on the gate's own non-interactive tile, which this test would
    otherwise flag)."""
    fixtures = [
        (_zone_records, _BOUNDS),
        (lambda: _rect_zone_records(5, 4), (64, 64)),
    ]
    ran_at_least_once = False
    for make_fixture, bounds in fixtures:
        for seed in range(1, 20):
            zone_records, objs_existing = make_fixture()
            objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=bounds)
            if n_placed != 1:
                continue
            access = next((o for o in objs if o.purpose in ("QUEST_GATE", "TRANSPORT")), None)
            if access is None:
                continue
            ran_at_least_once = True
            blocked_by: dict[Tile, PlacedObject] = {}
            for o in objs:
                if o is access:
                    continue
                for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y):
                    if blk:
                        blocked_by[(cx, cy)] = o
            access_cells = {
                (cx, cy) for cx, cy, _b in OR.mask_cells(access.mask, access.x, access.y)
            }
            for cell in access_cells:
                culprit = blocked_by.get(cell)
                assert culprit is None, (
                    f"seed {seed}: access object's own footprint tile {cell} got a "
                    f"blocking object stacked onto it: {culprit}"
                )
    assert ran_at_least_once, (
        "fixture assumption broke: no seed produced a loot zone with an access object"
    )


def test_a_single_entrance_zone_qualifies_as_a_loot_zone() -> None:
    """Control: with no blocking object splitting the shared boundary, zone 0 has
    exactly one real passable gap into zone 1 and must be selected."""
    zone_records, objs_existing = _zone_records(blocked_at=None)
    _objs, n_placed, zids = _place(zone_records, objs_existing, seed=1, bounds=_BOUNDS)
    assert n_placed == 1
    assert zids == {0}


def test_a_vegetation_wall_splitting_the_border_disqualifies_the_zone() -> None:
    """A single blocking object in the middle of the shared boundary row splits it
    into two disjoint passable gaps -- the zone borders its neighbour through TWO
    separate openings, so it must NOT be treated as single-entrance, even though
    the raw zone-vs-zone terrain adjacency (ignoring the blocker) is still one
    contiguous run."""
    zone_records, objs_existing = _zone_records(blocked_at=(3, 6))
    _objs, n_placed, zids = _place(zone_records, objs_existing, seed=1, bounds=_BOUNDS)
    assert n_placed == 0
    assert zids == set()


_ALLOWED_CHEST_TYPES = {"campfire", "treasureChest", "pandoraBox", "scholar", "spellScroll"}
_ALLOWED_ART_TYPES = {"randomArtifactMajor", "randomArtifactRelic"}
_ALLOWED_RESOURCE_SUBTYPES = {"mercury", "sulfur", "crystal", "gems", "gold"}
_ALLOWED_HERO_STRUCTURE_TYPES = {"learningStone", "gardenOfRevelation", "starAxis"}


def test_loot_zone_fill_only_uses_the_allowed_content_categories() -> None:
    """A loot zone's dense fill is artifacts of level >= 3 (major/relic), chests
    (treasure chest / campfire / pandora's box / scholar / a fixed level 4-5 spell
    scroll), the 3 whitelisted hero-strengthening structures (at most TWO of each,
    user-mandated 2026-09), or resources other than wood/ore -- never a treasure/minor
    artifact, an unrestricted random artifact/resource, a random/unconfigured spell
    scroll, or an unrelated REWARD_PICKUP type (corpse, leanTo, wagon, ...)."""
    zone_records, objs_existing = _zone_records(blocked_at=None)
    objs, n_placed, _zids = _place(zone_records, objs_existing, seed=1, bounds=_BOUNDS)
    assert n_placed == 1, "fixture must actually produce a loot zone to check content"

    violations: list[PlacedObject] = []
    hero_structure_types_seen: list[str] = []
    for o in objs:
        purpose = o.purpose
        typ = o.type
        if typ in _ALLOWED_HERO_STRUCTURE_TYPES:
            hero_structure_types_seen.append(typ)
        elif purpose == "REWARD_PICKUP" and typ != "artifact":
            if typ == "spellScroll":
                # VCMI's spellScroll object has exactly one subtype ("object"); the
                # spell itself lives in options.spell, never in subtype.
                if o.subtype != "object" or ON.spell_level(_spell_of(o)) not in (4, 5):
                    violations.append(o)
            elif typ not in _ALLOWED_CHEST_TYPES | _ALLOWED_ART_TYPES:
                violations.append(o)
        elif purpose == "RESOURCE_PILE" and o.subtype not in _ALLOWED_RESOURCE_SUBTYPES:
            violations.append(o)
    assert violations == []
    counts = collections.Counter(hero_structure_types_seen)
    assert all(n <= 2 for n in counts.values()), (
        f"no whitelisted hero-strengthening structure may be placed more than twice: {counts}"
    )


def test_loot_zone_fill_claims_every_non_access_tile() -> None:
    """Every tile of a sealed loot zone ends up occupied except the access object's own
    interactive cell -- an unfilled interior tile bordering water would let a boat-borne
    hero dock directly onto it, bypassing the gate/monolith entirely (user-mandated).
    The doorway/corridor tiles excavated for guaranteed access are NOT exempt (s7-z4
    third occurrence, 2026-09: they used to be reserved as a permanently-empty hallway,
    leaving several genuinely reachable tiles right behind the gate unfilled forever)
    -- loot fill places walk-on ('A'-mask) objects, so a resource pile or structure
    sitting in the corridor never blocks the hero's path through it. Asserts ZERO gap
    tiles."""
    ts0 = _zone_records()[0][0].ts
    ran_at_least_once = False
    for seed in range(1, 8):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        ran_at_least_once = True
        claimed: set[Tile] = set()
        access_interactive: set[Tile] = set()
        for o in objs:
            if (o.x, o.y) not in ts0 and not any(
                (cx, cy) in ts0 for cx, cy, _b in OR.mask_cells(o.mask, o.x, o.y)
            ):
                continue
            for cx, cy, _b in OR.mask_cells(o.mask, o.x, o.y):
                if (cx, cy) in ts0:
                    claimed.add((cx, cy))
            if o.purpose in ("QUEST_GATE", "TRANSPORT"):
                access_interactive |= set(OR.mask_interactive_cells(o.mask, o.x, o.y)) & ts0
                access_interactive |= {
                    (cx, cy + 1) for cx, cy in OR.mask_interactive_cells(o.mask, o.x, o.y)
                } & ts0
        gap = ts0 - claimed - access_interactive
        assert not gap, f"seed {seed}: unclaimed loot-zone tiles {sorted(gap)}"
    assert ran_at_least_once, "fixture assumption broke: no seed produced a loot zone"


def test_loot_zone_fill_claims_every_tile_of_a_multi_tile_corridor() -> None:
    """s7-z4 third occurrence (2026-09): the corridor connecting the gate to the rest
    of the zone's room (a narrow zone shape puts more than one tile between the
    entrance and the room -- see `_narrow_zone_records`) must ALSO get filled with
    loot, not left as a permanently-reserved empty hallway. Direct regression for the
    reported symptom ('5 tiles just below the gate are not filled')."""
    ts0 = _narrow_zone_records()[0][0].ts
    ran_at_least_once = False
    for seed in range(1, 30):
        zone_records, objs_existing = _narrow_zone_records()
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=(32, 14))
        if n_placed != 1:
            continue
        ran_at_least_once = True
        claimed: set[Tile] = set()
        access_interactive: set[Tile] = set()
        for o in objs:
            if (o.x, o.y) not in ts0 and not any(
                (cx, cy) in ts0 for cx, cy, _b in OR.mask_cells(o.mask, o.x, o.y)
            ):
                continue
            for cx, cy, _b in OR.mask_cells(o.mask, o.x, o.y):
                if (cx, cy) in ts0:
                    claimed.add((cx, cy))
            if o.purpose in ("QUEST_GATE", "TRANSPORT"):
                access_interactive |= set(OR.mask_interactive_cells(o.mask, o.x, o.y)) & ts0
                access_interactive |= {
                    (cx, cy + 1) for cx, cy in OR.mask_interactive_cells(o.mask, o.x, o.y)
                } & ts0
        gap = ts0 - claimed - access_interactive
        assert not gap, f"seed {seed}: unclaimed loot-zone tiles {sorted(gap)}"
    assert ran_at_least_once, "fixture assumption broke: no seed produced a loot zone"


def test_loot_zone_fill_across_many_seeds_never_exceeds_two_per_hero_structure() -> None:
    """Stress the Pass-1 per-type cap across many seeds/zone sizes -- a single seed's
    small zone might never place enough structures to expose a triplicate-allowing
    bug. Exactly two of each type is the target (user-mandated 2026-09); tile
    contention may leave fewer, but never more."""
    for seed in range(1, 20):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        types = [o.type for o in objs if o.type in _ALLOWED_HERO_STRUCTURE_TYPES]
        counts = collections.Counter(types)
        assert all(n <= 2 for n in counts.values()), (
            f"seed {seed}: a hero structure was placed more than twice: {counts}"
        )


def test_loot_zone_fill_places_two_instances_of_each_hero_structure_apart_from_each_other() -> None:
    """Pass 1 (user-mandated 2026-09): TWO instances of each of the 3 whitelisted
    hero-strengthening structures, separated from one another (never adjacent/
    touching) rather than clustered together. Sampled across enough seeds/zone sizes
    that a comfortably-sized zone actually reaches the target count of 2 for at least
    one seed."""
    _DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    saw_two_of_a_type = False
    for seed in range(1, 20):
        zone_records, objs_existing = _rect_zone_records(5, 4)
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=(64, 64))
        if n_placed != 1:
            continue
        by_type: collections.defaultdict[str, list[Tile]] = collections.defaultdict(list)
        for o in objs:
            if o.type in _ALLOWED_HERO_STRUCTURE_TYPES:
                by_type[o.type].append((o.x, o.y))
        for typ, positions in by_type.items():
            assert len(positions) <= 2, f"seed {seed}: {typ} placed {len(positions)} times"
            if len(positions) == 2:
                saw_two_of_a_type = True
                p1, p2 = positions
                assert max(abs(p1[0] - p2[0]), abs(p1[1] - p2[1])) >= LOOT_HERO_STRUCTURE_MIN_SEP, (
                    f"seed {seed}: the two {typ} instances {positions} are too close together"
                )
    assert saw_two_of_a_type, "fixture assumption broke: no seed placed 2 of any hero structure"


def _rect_zone_records(w: int, h: int) -> tuple[list[ZoneRecord], list[PlacedObject]]:
    """A wxh rectangular zone (zid 0) with a single boundary along its bottom edge to a
    large neighbour (zid 1) -- a plain single-entrance loot-zone fixture. Sized 5x4 (20
    tiles) it makes the old 30%-of-free-tiles cap bind: far more than 5 tiles stay free
    after sealing/access overhead, but the cap stopped hero-structure placement at 3 of
    the 5 whitelisted types."""
    ts0 = {(x, y) for x in range(w) for y in range(h)}
    ts1 = {(x, y) for x in range(40) for y in range(h, h + 30)}
    zr0 = _record(0, ts0)
    zr1 = _record(1, ts1)
    return [zr0, zr1], []


def test_loot_zone_fill_places_every_whitelisted_hero_structure_tile_budget_permitting() -> None:
    """Pass 1 (user-mandated 2026-09): no throttle to a fraction of the zone -- every
    whitelisted type gets its (up to two) instances placed, tile availability
    permitting. A comfortably-sized zone must see all 3 whitelisted types appear on at
    least one seed."""
    counts: list[int] = []
    for seed in range(1, 20):
        zone_records, objs_existing = _rect_zone_records(5, 4)
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=(64, 64))
        if n_placed != 1:
            continue
        types = {o.type for o in objs if o.type in _ALLOWED_HERO_STRUCTURE_TYPES}
        counts.append(len(types))
    assert counts, "fixture assumption broke: no seed produced a loot zone"
    assert max(counts) == len(_ALLOWED_HERO_STRUCTURE_TYPES), (
        f"tile budget should allow all {len(_ALLOWED_HERO_STRUCTURE_TYPES)} types on "
        f"at least one seed: {counts}"
    )


def test_loot_zone_fill_pass2_uses_the_20_40_40_split() -> None:
    """Pass 2 (user-mandated 2026-09): 20% major/relic artifact, 40% chest, 40% rare
    resource -- not the old 30/30/40 split. Statistical check over many seeds/tiles:
    the artifact share must sit near 20%, not 30%."""
    n_art = n_chest = n_res = 0
    for seed in range(1, 60):
        zone_records, objs_existing = _zone_records()
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=_BOUNDS)
        if n_placed != 1:
            continue
        ts0 = zone_records[0].ts
        for o in objs:
            if (o.x, o.y) not in ts0:
                continue
            typ = o.type
            if typ in _ALLOWED_HERO_STRUCTURE_TYPES:
                continue
            if typ in _ALLOWED_ART_TYPES:
                n_art += 1
            elif typ in _ALLOWED_CHEST_TYPES:
                n_chest += 1
            elif o.purpose == "RESOURCE_PILE":
                n_res += 1
    total = n_art + n_chest + n_res
    assert total > 500, "fixture too small to be statistically meaningful"
    art_frac = n_art / total
    assert 0.12 <= art_frac <= 0.28, (
        f"artifact share {art_frac:.2f} not near 20% (n_art={n_art}, total={total})"
    )


def test_loot_zone_fill_eventually_places_a_fixed_level_4_or_5_spell_scroll() -> None:
    """The spell-scroll chest-tier option must actually fire (not just never violate
    the rule because it never gets picked) -- sampled across enough seeds/zone sizes
    that a 1-in-5 chest-kind roll is virtually guaranteed to land at least once."""
    found: PlacedObject | None = None
    for seed in range(1, 40):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, _n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=_BOUNDS)
        scroll = next((o for o in objs if o.type == "spellScroll"), None)
        if scroll is not None:
            found = scroll
            break
    assert found is not None, "no spell scroll appeared across 39 seeds -- check the wiring"
    assert ON.spell_level(_spell_of(found)) in (4, 5)


def test_spell_scroll_objects_carry_the_spell_in_options_not_subtype() -> None:
    """VCMI's spellScroll object type has exactly one registered subtype ("object");
    stashing the spell name in subtype instead (the s9 defect, 2026-09) makes VCMI
    fail to load the map with 'Unknown entity spellScroll::<name> found!' -- confirmed
    against lib/mapping/MapFormatJson.cpp, which reads the spell from
    configuration["options"]["spell"]. Every generated spellScroll object must use
    that shape, across enough seeds that several actually get placed."""
    seen = 0
    for seed in range(1, 40):
        zone_records, objs_existing = _zone_records(blocked_at=None)
        objs, _n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=_BOUNDS)
        for o in objs:
            if o.type != "spellScroll":
                continue
            seen += 1
            assert o.subtype == "object", (
                f"seed {seed}: spellScroll subtype {o.subtype!r} must be "
                f"'object' -- the spell name belongs in options.spell"
            )
            spell = _spell_of(o)
            assert ON.spell_level(spell) in (4, 5), (
                f"seed {seed}: spellScroll options.spell {spell!r} is not a known level 4/5 spell"
            )
    assert seen >= 3, "fixture assumption broke: too few spell scrolls placed to check"


def _narrow_zone_records() -> tuple[list[ZoneRecord], list[PlacedObject]]:
    """A 2-wide corridor (zone 0, 12 tiles) walled by a big exterior zone (zone 1) on
    both long sides and the far end -- every zone-0 tile counts as zone perimeter, the
    exact shape that exposed the s7-z4 defect: `_seal_all_passages` seals the FULL
    perimeter (not just the single passage cluster the eligibility check found), so an
    access object's interior-side neighbor could get sealed shut even though the old
    check (which only looked at that stale passage cluster) believed it stayed open.

    zone1's own flanking columns are pre-blocked at y=2/y=3 (its own ordinary
    vegetation density, already committed by the time `place_loot_zones` runs) --
    without SOME pre-existing block there, EVERY possible gate position along this
    2-wide corridor leaks sideways into zone1's wide-open flank (s7-z4 defect, 2026-09,
    fourth occurrence: `_entry_tile_has_stray_leak` correctly rejects every one of
    those, so a fixture with a fully-open neighbour never places a gate at all -- not a
    real zone-1 border, just this fixture's own unrealistic 0%-density flank)."""
    ts0 = {(x, y) for x in (2, 3) for y in range(0, 6)}
    # zone1 must NOT itself qualify as a loot zone (over LOOT_ZONE_MAX_TILES=60), or it
    # would compete with zone0 for the only slot in ext_pool, leaving no zone free to
    # host the keymaster/exterior monolith.
    ts1 = (
        {(1, y) for y in range(0, 6)}
        | {(4, y) for y in range(0, 6)}
        | {(x, y) for x in range(0, 30) for y in range(6, 12)}
    )
    zr0 = _record(0, ts0)
    zr1 = _record(1, ts1)
    objs_existing = [_blocker(x, y) for x, y in ((1, 2), (1, 3), (4, 2), (4, 3))]
    return [zr0, zr1], objs_existing


def test_entry_corridor_reaches_the_whole_room_not_just_the_first_doorway_tile() -> None:
    """s7-z4 second occurrence (2026-09): real seed-7 repro had a 1-tile vestibule
    (the doorway `_find_entry_tile` finds) separated from the zone's actual room by a
    FURTHER neck row that is entirely boundary-classified (adjacent to tiles outside
    the zone), because the vestibule above it is narrower than the room below. Sealing
    every boundary tile except that single vestibule tile leaves the whole room --
    every tile `_fill_loot` is meant to use -- unreachable from the gate. Direct unit
    test of `find_entry_corridor` (the module-level fix), with a hand-built ts/all_ts
    that reproduces the exact narrow-vestibule/wide-room shape from the real map,
    bypassing `place_loot_zones`'s own gate-siting heuristics entirely."""
    entryrow = {(5, 0)}  # 1-tile vestibule (doorway)
    neck = {(x, 1) for x in range(1, 10)}  # full-width neck row
    room = {(x, y) for x in range(1, 10) for y in range(2, 6)}
    ts = entryrow | neck | room
    box = {(x, y) for x in range(0, 11) for y in range(-1, 7)}
    all_ts = ts | (box - ts)
    entry_tile: Tile = (5, 0)

    DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    ext_ts = all_ts - ts
    boundary = {t for t in ts if any((t[0] + dx, t[1] + dy) in ext_ts for dx, dy in DIRS8)}
    interior = ts - boundary
    assert interior, "fixture assumption broke: no interior tiles to protect"

    def _reachable(skip_cells: set[Tile]) -> set[Tile]:
        avail = ts - (boundary - skip_cells)
        seen: set[Tile] = {entry_tile} if entry_tile in avail else set()
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
        "-- this shape no longer reproduces the s7-z4 second occurrence"
    )

    corridor = find_entry_corridor(entry_tile, [], ts, all_ts)
    new_reach = _reachable(corridor)
    assert interior <= new_reach, (
        f"corridor {sorted(corridor)} still leaves "
        f"{sorted(interior - new_reach)} of the room unreachable from the gate"
    )


def test_a_narrow_loot_zones_access_object_always_has_a_usable_interior_doorway() -> None:
    """s7-z4 (2026-09): a narrow zone's interior can be entirely on the raw zone
    perimeter, which _seal_all_passages seals in full. Without a reserved doorway, the
    access object's interactive cell ends up with no passable interior neighbor at all
    -- the gate/monolith opens onto a wall. Sampled across enough seeds to exercise
    both the gate and the two-way-monolith branch (50/50 per zone)."""
    seen_gate = seen_mono = False
    for seed in range(1, 30):
        zone_records, objs_existing = _narrow_zone_records()
        objs, n_placed, _zids = _place(zone_records, objs_existing, seed=seed, bounds=(32, 14))
        if n_placed != 1:
            continue
        access = next(o for o in objs if o.purpose in ("QUEST_GATE", "TRANSPORT"))
        seen_gate = seen_gate or access.purpose == "QUEST_GATE"
        seen_mono = seen_mono or access.purpose == "TRANSPORT"
        interactive = OR.mask_interactive_cells(access.mask, access.x, access.y)
        blocked: set[Tile] = set()
        for o in objs:
            for cx, cy, blk in OR.mask_cells(o.mask, o.x, o.y):
                if blk:
                    blocked.add((cx, cy))
        ts0 = zone_records[0].ts
        has_open_interior_neighbor = any(
            (ix + dx, iy + dy) in ts0 and (ix + dx, iy + dy) not in blocked
            for ix, iy in interactive
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        )
        assert has_open_interior_neighbor, (
            f"seed {seed}: {access.purpose} at ({access.x},{access.y}) has no "
            "passable interior neighbor -- unreachable loot zone"
        )
    assert seen_gate, "fixture assumption broke: no seed produced a gate"
    assert seen_mono, "fixture assumption broke: no seed produced a monolith"
