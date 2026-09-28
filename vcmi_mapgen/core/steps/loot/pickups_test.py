"""Reliability tests for the guarded pocket caches and the scatter pickups under them."""

import os
import re
from dataclasses import replace

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import CoverIndex, Footprint, PlacedObject, Role, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.cells import legal_cells
from vcmi_mapgen.core.placement.scatter import ScatterConfig, ScatterZone, place_scatter
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.steps.loot import pickups as CA
from vcmi_mapgen.corpus.gameplay import STATS_PATH
from vcmi_mapgen.corpus.vegetation import PP_DIR

HAVE_STATS = os.path.exists(os.path.join(PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


def _pickups(catalog: Catalog, zone: ScatterZone, seed: int) -> list[PlacedObject]:
    cover = CoverIndex()
    sobjs, reach = place_scatter(catalog, zone, ScatterConfig(seed=seed, cover=cover))
    record = ZoneRecord(
        zid=1,
        terrain="grass",
        ts=frozenset(zone.ts),
        open_set=frozenset(zone.open_set),
        passable=frozenset(zone.open_set),
        reach=frozenset(reach),
    )
    cobjs, _n, _depths = CA.place_pocket_caches(
        catalog, [record], seed=seed, context=CA.PocketContext(existing_objs=sobjs, cover=cover)
    )
    return sobjs + cobjs


@needs_stats
def test_pickup_layer_legal_and_deterministic(catalog: Catalog) -> None:

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    label = label_zones({1: _zone(ts)})
    # synthetic open field with a sealed-off pocket-ish structure: a web cross + nooks
    prot = {(x, 12) for x in range(30)} | {(15, y) for y in range(24)}
    open_set = set(ts)
    o1 = _pickups(catalog, ScatterZone(ts, label, 1, "grass", open_set, prot), seed=6)
    o2 = _pickups(catalog, ScatterZone(ts, label, 1, "grass", open_set, prot), seed=6)
    assert o1 == o2, "pickup layer must be seed-deterministic"
    assert o1, "a 720-tile grass zone should hold pickups"

    used: set[Tile] = set()
    no_used: set[Tile] = set()
    for o in o1:
        if o.purpose == Purpose.GUARD:
            # a guard's decorative sprite-bleed cells MAY overlap terrain or already-placed
            # cache pickups (the pocket it seals is packed by design); only its interactive
            # cell — the tile the monster actually stands on — must be free and unique
            inter = FP.interactive_cells(o.footprint, o.x, o.y)
            assert inter and used.isdisjoint(inter), "guard stand-tile must be free"
            used.update(inter)
            assert (o.x, o.y) not in prot, "guards must not sit on the mandatory web"
            continue
        cells = legal_cells(
            replace(catalog.identity_of(o.kind), footprint=o.footprint),
            (o.x, o.y),
            open_set,
            no_used,
        )
        assert cells is not None, "footprint must lie on open tiles"
        assert used.isdisjoint(cells), "pickups must not overlap each other"
        used.update(cells)


def _zone(ts: set[Tile]) -> Zone:
    return Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(14.5, 11.5),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def _obj(x: int, y: int, purpose: str, kind: str) -> PlacedObject:
    return PlacedObject(
        x=x,
        y=y,
        level=0,
        purpose=purpose,
        kind=kind,
        footprint=Footprint.one(Role.VISIT),
    )


@needs_stats
def test_scatter_places_resource_piles(catalog: Catalog) -> None:
    """Unguarded scatter places resource piles, a mix of fixed and random resources, and
    a real zone always yields some."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    label = label_zones({1: _zone(ts)})
    prot = {(x, 12) for x in range(30)} | {(15, y) for y in range(24)}
    piles: list[PlacedObject] = []
    for seed in range(1, 10):
        objs = _pickups(catalog, ScatterZone(ts, label, 1, "grass", set(ts), prot), seed=seed)
        piles += [o for o in objs if o.purpose == Purpose.RESOURCE_PILE]
    assert piles, "a 720-tile zone (>= LOOT_FLOOR_AREA) must yield resource piles"
    assert not any(o.cache for o in piles), "scatter piles are unguarded"
    assert any(catalog.identity_of(o.kind).type == "resource" for o in piles), (
        "fixed resource piles must appear"
    )


def _type_of(catalog: Catalog, o: PlacedObject) -> str:
    return catalog.identity_of(o.kind).type or ""


def _field_with_room(
    room: set[Tile], mouth: set[Tile], field_w: int = 15, field_h: int = 4
) -> ZoneRecord:
    field = {(x, y) for x in range(field_w) for y in range(field_h)}
    ts = field | set(mouth) | set(room)
    return ZoneRecord(
        zid=0,
        terrain="grass",
        ts=frozenset(ts),
        open_set=frozenset(ts),
        passable=frozenset(ts),
        reach=frozenset(ts),
    )


@needs_stats
def test_pocket_guard_level_matches_artifact_tier_exactly(catalog: Catalog) -> None:
    """Level of the guard monster == level of the artifact at the deep end (user-mandated
    2026-09) -- no random +1 bump on the guard, unlike the pre-redefinition behavior."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}  # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    objs, n_pockets, _depth = CA.place_pocket_caches(catalog, [zr], seed=3, bounds=(20, 20))
    assert n_pockets == 1, "fixture assumption broke: expected exactly one pocket"
    guard = next(o for o in objs if o.purpose == Purpose.GUARD)
    art = next(
        o
        for o in objs
        if o.purpose == Purpose.REWARD_PICKUP and "artifact" in _type_of(catalog, o).lower()
    )
    match = re.match(r"randomMonsterLevel(\d)", _type_of(catalog, guard))
    assert match is not None
    glvl = int(match.group(1))
    want = catalog.random_artifact(CA.ART_TIER_BY_GUARD_LEVEL[glvl - 1]).kind
    assert art.kind == want, (
        f"guard is level {glvl} but artifact animation {art.kind!r} doesn't "
        f"match that tier ({want!r})"
    )


@needs_stats
def test_pocket_overlay_depth_is_only_recorded_for_pockets_that_actually_get_filled(
    catalog: Catalog,
) -> None:
    """Bug (2026-09, 'not all magenta pocket tiles are filled'): `pocket_depth_by_tile`
    -- the map PocketOverlay renders straight from -- used to be written before the
    late gates that can still `continue` out of a candidate (every pocket tile already
    claimed by an earlier pass, so `cache_spots` ends up empty; or no guard fits). A
    pocket that fails one of those gates got zero objects placed on it, yet every one
    of its tiles was still recorded as pocket depth -- painted magenta with nothing
    underneath. Fixture: pre-claim every room tile as already claimed (simulating an
    earlier pass having spent it), so the accepted-candidate gates find no cache spots
    left and the whole pocket must be dropped, both from `objs` and from `depth`."""

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}  # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    objs, _n_pockets, depth = CA.place_pocket_caches(
        catalog,
        [zr],
        seed=3,
        bounds=(20, 20),
        context=CA.PocketContext(cover=CoverIndex(claims=room)),
    )
    assert not any(o.purpose == Purpose.GUARD for o in objs)
    assert not depth, f"pocket tiles marked magenta with nothing placed: {sorted(depth)}"


@needs_stats
def test_pocket_overlay_never_marks_an_approach_reserved_tile_that_cant_receive_a_cache(
    catalog: Catalog,
) -> None:
    """Same class of bug as above, at single-tile granularity (real seed-7 repro,
    2026-09: a pocket's deepest tile sat right against an existing STAT_PERMANENT
    structure's approach cell). `cache_spots`/`avail` were selected against
    `global_reach8` (physically walkable), but the actual placement calls gate on the
    STRICTER `global_place` (`global_reach8 & global_open`) -- so a pocket tile that is
    walkable but reserved as another object's approach cell (excluded from open_set)
    was always destined to fail placement, yet still got recorded as pocket depth."""

    room = {(5, 5), (6, 5), (5, 6), (6, 6), (5, 7), (6, 7)}  # 6-tile cavity
    zr = _field_with_room(room, {(5, 4), (6, 4)})
    zr = replace(zr, open_set=zr.open_set - {(6, 7)})  # walkable (still in ts/passable/reach) but
    # reserved -- e.g. another object's approach cell
    objs, _n_pockets, depth = CA.place_pocket_caches(catalog, [zr], seed=3, bounds=(20, 20))
    claimed: set[Tile] = set()
    for o in objs:
        for cx, cy, _b in FP.anchored_cells(o.footprint, o.x, o.y):
            claimed.add((cx, cy))
    unfilled = set(depth) - claimed
    assert not unfilled, f"pocket tiles marked magenta with nothing placed: {unfilled}"


def test_pocket_guard_never_cuts_a_town_off_from_its_own_starting_mine(catalog: Catalog) -> None:
    """s2-z1 diagnosis (2026-09): a pocket declared right by the castle got guarded,
    and that guard happened to seal the ONLY isthmus connecting the town to its own
    force_town sawmill, even though the sawmill already carries its own dedicated
    level-1 guard. Only the tile a guard stands on blocks; its zone of control does not
    (user-mandated 2026-09). Fixture: two open rooms joined by a single 3-tile isthmus
    (6,4)-(8,4), with a 1-tile pocket above it at (7,2)/(7,3). TOWN is in the left room,
    a sawmill MINE in the right room."""

    left = {(x, y) for x in range(6) for y in range(9)}
    right = {(x, y) for x in range(9, 15) for y in range(9)}
    isthmus = {(6, 4), (7, 4), (8, 4)}
    room = {(7, 2)}
    mouth_extra = {(7, 3)}
    ts = left | right | isthmus | room | mouth_extra

    town = _obj(2, 2, Purpose.TOWN, catalog.random_town().kind)
    mine = _obj(12, 2, Purpose.MINE, catalog.mines_by_resource("grass")["sawmill"][0].kind)
    zr = ZoneRecord(
        zid=0,
        terrain="grass",
        ts=frozenset(ts),
        open_set=frozenset(ts),
        passable=frozenset(ts),
        reach=frozenset(ts),
    )

    objs, _n_pockets, _depth = CA.place_pocket_caches(
        catalog,
        [zr],
        seed=3,
        bounds=(20, 20),
        context=CA.PocketContext(existing_objs=[town, mine], home_zids={0}),
    )

    stands = {
        c
        for o in objs
        if o.purpose == Purpose.GUARD
        for c in FP.interactive_cells(o.footprint, o.x, o.y)
    }
    open_tiles = ts - stands
    seen = {(0, 8)}
    frontier = [(0, 8)]
    while frontier:
        x, y = frontier.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in open_tiles and n not in seen:
                    seen.add(n)
                    frontier.append(n)
    assert (14, 8) in seen, (
        f"pocket guards standing on {stands} cut the town off from its own starting mine"
    )


@needs_stats
def test_pocket_chest_fill_uses_only_the_allowed_types(catalog: Catalog) -> None:
    """The cavity's non-artifact/non-resource fill is entirely chests/pandora's box
    (treasureChest, campfire, pandoraBox) -- never scholar/corpse/spellScroll/leanTo/
    wagon/warriorTomb/denOfThieves, which "everything but an artifact" used to allow."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")

    allowed = {"treasureChest", "campfire", "pandoraBox"}
    violations: list[PlacedObject] = []
    for seed in range(1, 15):
        room = {(x, y) for x in range(5, 7) for y in range(5, 10)}  # 10-tile cavity
        zr = _field_with_room(room, {(5, 4), (6, 4)})
        objs, _n_pockets, _depth = CA.place_pocket_caches(catalog, [zr], seed=seed, bounds=(20, 20))
        for o in objs:
            if (
                o.purpose == Purpose.REWARD_PICKUP
                and "artifact" not in _type_of(catalog, o).lower()
                and _type_of(catalog, o) not in allowed
            ):
                violations.append(o)
    assert violations == []
