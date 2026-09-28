"""Reliability tests for the gameplay draw and placement of one open zone."""

import os

import pytest

from vcmi_mapgen.conftest import OpenZone, OpenZonePlacer
from vcmi_mapgen.core.model import Footprint, Identity, PlacedObject, Role, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.footprint import footprint_cells
from vcmi_mapgen.core.placement.guards import GAP
from vcmi_mapgen.core.steps.vegetation import stats as PS
from vcmi_mapgen.corpus.gameplay import STATS_PATH, load_gameplay

HAVE_STATS = os.path.exists(os.path.join(PS.PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


def _footprint(o: PlacedObject) -> tuple[list[Tile], list[Tile], Tile | None]:

    return footprint_cells(Identity(o.type, o.subtype, o.animation, o.footprint), o.x, o.y)


@needs_stats
def test_gameplay_layer_legal_and_deterministic(open_zone: OpenZonePlacer) -> None:

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    o1 = open_zone(OpenZone(ts, "grass"), 4)
    o2 = open_zone(OpenZone(ts, "grass"), 4)
    assert o1 == o2, "gameplay placement must be seed-deterministic"
    objs, occupied, blocked, approaches = o1.gobjs, o1.occupied, o1.gblocked, o1.approaches
    assert objs, "a 720-tile grass zone should hold gameplay"
    # GUARD monsters deliberately sit ON approaches/gates, and MINE_SEAL decorations
    # deliberately sit GAP-adjacent to the mine they seal off (no approach of their own) —
    # the rigid rules below apply to the buildings only.
    core = [o for o in objs if o.purpose not in (Purpose.GUARD, Purpose.MINE_SEAL)]
    for g in (o for o in objs if o.purpose == Purpose.GUARD):
        # monster masks are V-padded to the sprite's tile extent (ground truth from
        # Maps/RandomMaps: every creature mask is ['VV', 'VA']), not a bare single cell.
        assert (g.x, g.y) in ts and g.footprint.grid() == (
            (Role.OVERLAY, Role.OVERLAY),
            (Role.OVERLAY, Role.VISIT),
        )
        assert (g.type or "").startswith("randomMonster"), "guards are random monsters"
    for s in (o for o in objs if o.purpose == Purpose.MINE_SEAL):
        assert (s.x, s.y) in ts and s.footprint == Footprint.one(Role.BLOCKING), (
            "a mine seal is a single blocking cell"
        )
    # rigid rules: footprints in-zone, no overlap, approach tile free and in-zone
    seen: set[Tile] = set()
    for o in core:
        allc, _blk, approach = _footprint(o)
        assert approach is not None and approach in ts
        for cell in allc:
            assert cell in ts and cell not in seen
        seen.update(allc)
    # a hero must be able to stand on every approach tile: never under a blocking cell
    assert set(approaches).isdisjoint(blocked)
    assert blocked <= occupied
    # separation: at least GAP free tiles between the blocking cells of any two footprints
    per_obj: list[list[Tile]] = []
    for o in core:
        _allc, blk, _a = _footprint(o)
        if blk:
            per_obj.append(blk)
    for i in range(len(per_obj)):
        for j in range(i + 1, len(per_obj)):
            d = min(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a in per_obj[i] for b in per_obj[j])
            assert d > GAP, f"objects {i},{j} too close (cheb {d})"


@needs_stats
def test_forced_town_sits_on_zone_centroid(open_zone: OpenZonePlacer) -> None:
    """A designated player zone gets its town ON the centroid (footprint-centered)."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    objs = open_zone(OpenZone(ts, "grass", player=True), 4).gobjs
    towns = [o for o in objs if o.purpose == Purpose.TOWN]
    assert towns, "force_town guarantees a town in a 720-tile zone"
    t = towns[0]
    # player start towns are ALWAYS randomTown: VCMI resolves an owned random town to the
    # lobby faction pick — a concrete start town would override the player's choice
    assert t.type == "randomTown", f"forced town must be randomTown, got {t.type}"
    mh = t.footprint.height
    mw = t.footprint.width
    fx = t.x - (mw - 1) / 2.0  # footprint centre (bottom-right anchor)
    fy = t.y - (mh - 1) / 2.0
    assert abs(fx - 14.5) <= 1.5 and abs(fy - 11.5) <= 1.5, (
        f"town footprint centre ({fx},{fy}) must sit on the centroid (14.5,11.5)"
    )


@needs_stats
def test_town_zone_gets_wood_and_ore_next_to_town(open_zone: OpenZonePlacer) -> None:
    """A zone with a town ALWAYS holds a sawmill + ore pit, anchored near the town."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    for seed in (1, 4, 9):
        objs = open_zone(OpenZone(ts, "grass", player=True), seed).gobjs
        towns = [o for o in objs if o.purpose == Purpose.TOWN]
        assert towns, f"seed {seed}: forced town missing"
        subs = {o.subtype for o in objs if o.purpose == Purpose.MINE}
        assert {"sawmill", "orePit"} <= subs, f"seed {seed}: economy pair missing ({subs})"
        t = towns[0]
        for m in (
            o for o in objs if o.purpose == Purpose.MINE and o.subtype in ("sawmill", "orePit")
        ):
            d = max(abs(m.x - t.x), abs(m.y - t.y))
            assert d <= 12, f"seed {seed}: {m.subtype} is {d} tiles from the town"


@needs_stats
def test_banks_placed_on_land_and_legal(open_zone: OpenZonePlacer) -> None:
    """Creature banks (utopias, conservatories, crypts...) place on land like visitables:
    full footprint in-zone, approach standable, no extra approach guard."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(45) for y in range(40)}
    banks: list[PlacedObject] = []
    for seed in range(1, 12):
        banks += [
            o for o in open_zone(OpenZone(ts, "grass"), seed).gobjs if o.purpose == Purpose.BANK
        ]
    assert banks, "a 1800-tile grass zone must produce banks across a dozen seeds"
    for b in banks:
        allc, _blk, approach = _footprint(b)
        assert approach is not None and all(c in ts for c in allc)


@needs_stats
def test_mine_sprites_match_terrain(open_zone: OpenZonePlacer) -> None:
    """Mine DEFs carry a baked-in terrain apron; placed mines must use variants the corpus
    actually uses on that terrain (no dirt-apron gold mine on grass)."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    st = load_gameplay()
    ts = {(x, y) for x in range(40) for y in range(30)}
    for terrain in ("grass", "snow"):
        mw = st[terrain].anim_w[Purpose.MINE]
        for seed in range(1, 8):
            objs = open_zone(OpenZone(ts, terrain), seed).gobjs
            for m in (o for o in objs if o.purpose == Purpose.MINE):
                w = mw.get(m.animation.lower(), 0)
                assert w > 0, (
                    f"{terrain}: mine variant {m.animation} "
                    f"({m.subtype}) never used on {terrain} in the corpus"
                )
