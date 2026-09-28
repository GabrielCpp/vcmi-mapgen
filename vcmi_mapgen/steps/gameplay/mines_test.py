"""Reliability tests for steps.gameplay.mines (L3 gameplay placement + corpus stats)."""

import os

import pytest

from vcmi_mapgen.models import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.steps.gameplay import mines as PG
from vcmi_mapgen.steps.gameplay.step import place_open_zone
from vcmi_mapgen.steps.gate.gates import GAP, footprint_cells
from vcmi_mapgen.steps.vegetation import stats as PS

HAVE_STATS = os.path.exists(os.path.join(PS.PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


def _footprint(o: PlacedObject) -> tuple[list[Tile], list[Tile], Tile | None]:

    return footprint_cells(Identity(o.type, o.subtype, o.animation, o.mask), o.x, o.y)


@needs_stats
def test_gameplay_layer_legal_and_deterministic() -> None:

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    o1 = place_open_zone(ts, "grass", 4)
    o2 = place_open_zone(ts, "grass", 4)
    assert o1 == o2, "gameplay placement must be seed-deterministic"
    objs, occupied, blocked, approaches = o1.gobjs, o1.occupied, o1.gblocked, o1.approaches
    assert objs, "a 720-tile grass zone should hold gameplay"
    # GUARD monsters deliberately sit ON approaches/gates, and MINE_SEAL decorations
    # deliberately sit GAP-adjacent to the mine they seal off (no approach of their own) —
    # the rigid rules below apply to the buildings only.
    core = [o for o in objs if o.purpose not in ("GUARD", "MINE_SEAL")]
    for g in (o for o in objs if o.purpose == "GUARD"):
        # monster masks are V-padded to the sprite's tile extent (ground truth from
        # Maps/RandomMaps: every creature mask is ['VV', 'VA']), not a bare single cell.
        assert (g.x, g.y) in ts and g.mask == ("VV", "VA")
        assert (g.type or "").startswith("randomMonster"), "guards are random monsters"
    for s in (o for o in objs if o.purpose == "MINE_SEAL"):
        assert (s.x, s.y) in ts and s.mask == ("B",), "a mine seal is a single blocking cell"
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


def test_select_player_zones_far_apart() -> None:
    """Player zones must be big AND mutually far apart — never all clustered together."""

    def zone(cx: float, cy: float, area: int) -> Zone:
        return Zone(terrain_type=2, area=area, centroid=(cx, cy), tiles=[], tiles_set=frozenset())

    zones = {
        0: zone(36, 36, 500),  # big centre
        1: zone(4, 4, 220),
        2: zone(68, 4, 200),
        3: zone(4, 68, 200),
        4: zone(68, 68, 220),
        5: zone(40, 40, 300),  # big but right NEXT to the centre
        6: zone(30, 30, 40),
    }  # too small: never a start
    zones_by_level = {0: zones}
    picks = PG.select_player_zones(zones_by_level, 2)
    assert picks[0] == (0, 0), "first pick is the largest zone"
    assert picks[1][1] in (1, 2, 3, 4), "second pick is a far corner, not the adjacent zone 5"
    picks4 = PG.select_player_zones(zones_by_level, 4)
    zids4 = [zid for _l, zid in picks4]
    assert 6 not in zids4 and 5 not in zids4, "small/adjacent zones lose to far corners"
    cents = [zones[zid].centroid for _l, zid in picks4]
    dmin = min(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 for i, a in enumerate(cents) for b in cents[i + 1 :]
    )
    assert dmin >= 32**2, "chosen starts keep real distance between them"
    assert PG.select_player_zones(zones_by_level, 2) == picks, "selection is deterministic"


@needs_stats
def test_forced_town_sits_on_zone_centroid() -> None:
    """A designated player zone gets its town ON the centroid (footprint-centered)."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    objs = place_open_zone(ts, "grass", 4, player=True).gobjs
    towns = [o for o in objs if o.purpose == "TOWN"]
    assert towns, "force_town guarantees a town in a 720-tile zone"
    t = towns[0]
    # player start towns are ALWAYS randomTown: VCMI resolves an owned random town to the
    # lobby faction pick — a concrete start town would override the player's choice
    assert t.type == "randomTown", f"forced town must be randomTown, got {t.type}"
    mh = len(t.mask)
    mw = max(len(r) for r in t.mask)
    fx = t.x - (mw - 1) / 2.0  # footprint centre (bottom-right anchor)
    fy = t.y - (mh - 1) / 2.0
    assert abs(fx - 14.5) <= 1.5 and abs(fy - 11.5) <= 1.5, (
        f"town footprint centre ({fx},{fy}) must sit on the centroid (14.5,11.5)"
    )


@needs_stats
def test_town_zone_gets_wood_and_ore_next_to_town() -> None:
    """A zone with a town ALWAYS holds a sawmill + ore pit, anchored near the town."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    for seed in (1, 4, 9):
        objs = place_open_zone(ts, "grass", seed, player=True).gobjs
        towns = [o for o in objs if o.purpose == "TOWN"]
        assert towns, f"seed {seed}: forced town missing"
        subs = {o.subtype for o in objs if o.purpose == "MINE"}
        assert {"sawmill", "orePit"} <= subs, f"seed {seed}: economy pair missing ({subs})"
        t = towns[0]
        for m in (o for o in objs if o.purpose == "MINE" and o.subtype in ("sawmill", "orePit")):
            d = max(abs(m.x - t.x), abs(m.y - t.y))
            assert d <= 12, f"seed {seed}: {m.subtype} is {d} tiles from the town"


@needs_stats
def test_mine_ledger_covers_basics_and_rations_gold() -> None:
    """The map-level ledger drives zones to cover all six basic resources and blocks gold
    mines until the map holds several towns."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(40) for y in range(30)}
    # gold is rationed to towns - 1 (a zone may roll a neutral town of its own, which
    # legitimately raises the quota — the INVARIANT is what must hold)
    for seed in range(1, 8):
        ledger = PG.Ledger(missing=set(PG.BASIC_MINE_RES), towns=1, gold=0)
        objs = place_open_zone(ts, "grass", seed, ledger=ledger).gobjs
        n_gold = sum(1 for o in objs if o.purpose == "MINE" and o.subtype == "goldMine")
        assert n_gold <= ledger.gold <= max(0, ledger.towns - 1), (
            f"seed {seed}: gold {n_gold} exceeds quota (towns={ledger.towns})"
        )
    # missing basics are drawn FIRST: a fresh ledger shrinks by every mine the zone placed
    ledger = PG.Ledger(missing=set(PG.BASIC_MINE_RES), towns=1, gold=0)
    objs = place_open_zone(ts, "grass", 3, ledger=ledger).gobjs
    n_mines = sum(1 for o in objs if o.purpose == "MINE")
    assert len(ledger.missing) <= max(0, len(PG.BASIC_MINE_RES) - n_mines), (
        "every placed mine must come from the missing set while it is non-empty"
    )


@needs_stats
def test_banks_placed_on_land_and_legal() -> None:
    """Creature banks (utopias, conservatories, crypts...) place on land like visitables:
    full footprint in-zone, approach standable, no extra approach guard."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(45) for y in range(40)}
    banks: list[PlacedObject] = []
    for seed in range(1, 12):
        banks += [o for o in place_open_zone(ts, "grass", seed).gobjs if o.purpose == "BANK"]
    assert banks, "a 1800-tile grass zone must produce banks across a dozen seeds"
    for b in banks:
        allc, _blk, approach = _footprint(b)
        assert approach is not None and all(c in ts for c in allc)


@needs_stats
def test_mine_sprites_match_terrain() -> None:
    """Mine DEFs carry a baked-in terrain apron; placed mines must use variants the corpus
    actually uses on that terrain (no dirt-apron gold mine on grass)."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    st = PG.load_gameplay()
    ts = {(x, y) for x in range(40) for y in range(30)}
    for terrain in ("grass", "snow"):
        mw = st[terrain].anim_w["MINE"]
        for seed in range(1, 8):
            objs = place_open_zone(ts, terrain, seed).gobjs
            for m in (o for o in objs if o.purpose == "MINE"):
                w = mw.get(m.animation.lower(), 0)
                assert w > 0, (
                    f"{terrain}: mine variant {m.animation} "
                    f"({m.subtype}) never used on {terrain} in the corpus"
                )


@needs_stats
def test_audit_variety_green() -> None:
    """Every corpus (purpose, animation) on land must be reachable through the generator
    (identity via the ontology, placement via a pool) — the acceptance check for corpus
    visitable variety."""

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    gaps = PG.audit_variety()
    assert gaps == [], f"variety gaps: {gaps}"
