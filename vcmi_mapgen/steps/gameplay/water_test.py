"""Reliability tests for steps.gameplay.water (water-body population + seaport guarantee)."""
import random
import zlib


def _water_and_land_zone():
    """A real (small, texture-skipped for speed) generated grid with a big water body and
    a big bordering land zone — real terrain generation gives an organic, jagged coastline,
    which `_ensure_water_seaports`'s anchor search needs (a perfectly straight synthetic
    coastline can leave its 3x3-footprint anchor just out of that search's 1-hop reach)."""
    from vcmi_mapgen.steps.gameplay import water as WT
    from vcmi_mapgen.steps.terrain_gen import macro_topo as MT

    WATER = 8
    grid = MT.generate(40, 40, seed=2, water_mode="islands", level=0, texture=False)
    H, W = len(grid), len(grid[0])
    water_tiles = {(x, y) for y in range(H) for x in range(W) if grid[y][x] == WATER}
    land_tiles = {(x, y) for y in range(H) for x in range(W) if grid[y][x] != WATER}
    NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
    border_land = {
        (x + dx, y + dy) for x, y in water_tiles for dx, dy in NB4
        if (x + dx, y + dy) in land_tiles
    }
    start = next(iter(border_land))
    zone_tiles = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in NB4:
            n = (x + dx, y + dy)
            if n in land_tiles and n not in zone_tiles:
                zone_tiles.add(n)
                stack.append(n)
    zones = {0: {"terrain_type": 2, "tiles_set": zone_tiles, "area": len(zone_tiles),
                 "centroid": (W / 2, H / 2)}}
    assert len(water_tiles) >= WT._SEA_ZONE_MIN_AREA and len(zone_tiles) >= WT._SEA_ZONE_MIN_AREA
    return WT, W, H, grid, zones


def _synthetic_sea_and_land(sea_tiles: int):
    """A precisely-sized square lake (`sea_tiles`) surrounded by a much bigger land mass
    -- used where the exact water-body tile count must straddle a threshold (real
    generation can't be sized precisely). A straight-line coastline (two adjacent bands)
    has NO valid shipyard anchor anywhere, regardless of area: the mask ('VVV'/'VVV'/
    'BXB', anchored at its bottom-right 'B') needs its dock row adjacent to water while
    its approach tile (one south of the dock) stays on land, which a straight shore can't
    satisfy in either orientation. A small lake fully enclosed by land gives the search a
    shoreline with real corners, the same way a solid rectangular island (surrounded by
    water on every side) already does for the island tests below."""
    from vcmi_mapgen.steps.gameplay import water as WT

    WATER, LAND = 8, 2
    lake_w = 1
    while lake_w * lake_w < sea_tiles:
        lake_w += 1
    margin = 6
    W = H = lake_w + margin * 2
    grid = [[LAND for _ in range(W)] for _ in range(H)]
    placed = 0
    for y in range(margin, margin + lake_w):
        for x in range(margin, margin + lake_w):
            if placed >= sea_tiles:
                break
            grid[y][x] = WATER
            placed += 1
    # Leave the outermost 1-tile ring OUT of the zone (still land, just unassigned) --
    # otherwise every non-zone neighbour anywhere is the lake (water), which trivially
    # satisfies `_ensure_water_seaports`'s is_island check (an "island" is a zone whose
    # every non-member neighbour is water/rock) and the land mass gets placed via the
    # ISLAND branch regardless of the lake's own size, testing the wrong rule.
    zone_tiles = {(x, y) for y in range(1, H - 1) for x in range(1, W - 1)
                  if grid[y][x] == LAND}
    zones = {0: {"terrain_type": 2, "tiles_set": zone_tiles, "area": len(zone_tiles),
                 "centroid": (W / 2, H / 2)}}
    return WT, W, H, grid, zones


def test_sea_zone_below_50_tiles_gets_no_seaport():
    from vcmi_mapgen.ontology import Ontology

    WT, W, H, grid, zones = _synthetic_sea_and_land(sea_tiles=40)
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    assert not objs, "a water body under 50 tiles must not get a seaport"


def test_sea_zone_50_or_more_gets_a_seaport():
    from vcmi_mapgen.ontology import Ontology

    WT, W, H, grid, zones = _synthetic_sea_and_land(sea_tiles=55)
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    assert objs, "a water body of 55 tiles must get a seaport"


def test_island_below_50_tiles_gets_no_seaport():
    """A tight 1-tile water margin around the island (not a wide open sea) -- otherwise
    the surrounding water body is itself >= _SEA_ZONE_MIN_AREA and the water-body
    guarantee (rule 1) places a seaport regardless of the island's own size, which would
    test the wrong rule."""
    from vcmi_mapgen.ontology import Ontology
    from vcmi_mapgen.steps.gameplay import water as WT

    WATER = 8
    W, H = 10, 7   # 40-tile island (5x8) + a 1-tile water ring = 30 water tiles, both < 50
    grid = [[WATER for _ in range(W)] for _ in range(H)]
    zone_tiles = {(x, y) for y in range(1, 6) for x in range(1, 9)}   # 40 tiles
    for x, y in zone_tiles:
        grid[y][x] = 2
    zones = {0: {"terrain_type": 2, "tiles_set": zone_tiles, "area": len(zone_tiles),
                 "centroid": (5, 3)}}
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    assert not objs, "a 40-tile island must not get a seaport (threshold is 50)"


def test_island_50_or_more_tiles_gets_a_seaport():
    from vcmi_mapgen.ontology import Ontology
    from vcmi_mapgen.steps.gameplay import water as WT

    WATER = 8
    W = H = 14
    grid = [[WATER for _ in range(W)] for _ in range(H)]
    zone_tiles = {(x, y) for y in range(6) for x in range(9)}   # 54 tiles
    for x, y in zone_tiles:
        grid[y][x] = 2
    zones = {0: {"terrain_type": 2, "tiles_set": zone_tiles, "area": len(zone_tiles),
                 "centroid": (4, 3)}}
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    assert objs, "a 54-tile island must get a seaport"


def _comps_of(tiles, dirs, universe):
    """8- or 4-connected clusters of `tiles`, restricted to `universe`."""
    import collections
    seen, out = set(), []
    for t in sorted(tiles):
        if t in seen:
            continue
        c = {t}
        q = [t]
        seen.add(t)
        while q:
            x, y = q.pop()
            for dx, dy in dirs:
                n = (x + dx, y + dy)
                if n in universe and n not in seen:
                    seen.add(n)
                    c.add(n)
                    q.append(n)
        out.append(c)
    return out


def _two_islands_one_split_thin(seed=2, size=70, strip_w=2):
    """Two separate islands (shores) bordering the SAME big sea, with the second
    island (`lmB`) split into thin (`strip_w`-wide) vertical zones -- each too narrow
    to fit a shipyard's 3-wide footprint alone, but the shore as a whole (spanning all
    of them) plainly has room, the same way a real 72x72 map's zones 4/5/6/7 (s10
    diagnosis, 2026-09) each individually failed placement on their own shore slice."""
    from vcmi_mapgen.steps.gameplay import water as WT
    from vcmi_mapgen.steps.terrain_gen import macro_topo as MT

    WATER = 8
    NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
    DIRS8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))

    grid = MT.generate(size, size, seed=seed, water_mode="islands", level=0, texture=False)
    H, W = len(grid), len(grid[0])
    water_tiles = {(x, y) for y in range(H) for x in range(W) if grid[y][x] == WATER}
    land_tiles = {(x, y) for y in range(H) for x in range(W) if grid[y][x] != WATER}

    water_comps = sorted(_comps_of(water_tiles, NB4, water_tiles), key=len, reverse=True)
    big = water_comps[0]
    shore = set()
    for wx, wy in big:
        for dx, dy in NB4:
            t = (wx + dx, wy + dy)
            if t in land_tiles:
                shore.add(t)
    shore_clusters = sorted(_comps_of(shore, DIRS8, shore), key=len, reverse=True)
    usable = [c for c in shore_clusters if len(c) >= 50]
    assert len(usable) >= 2, "fixture assumption broke: need >=2 separate shores"

    land_comps = _comps_of(land_tiles, NB4, land_tiles)

    def landmass_for(shore_cluster):
        s = next(iter(shore_cluster))
        return next(lc for lc in land_comps if s in lc)

    lm_a = landmass_for(usable[0])
    lm_b = landmass_for(usable[1])

    zones = {0: {"terrain_type": 2, "tiles_set": lm_a, "area": len(lm_a),
                "centroid": (0, 0)}}
    sub = {}
    for t in lm_b:
        sub.setdefault(t[0] // strip_w, set()).add(t)
    for i, ts in enumerate(sub.values(), start=1):
        zones[i] = {"terrain_type": 2, "tiles_set": ts, "area": len(ts), "centroid": (0, 0)}
    # strip_w=2 is structurally narrower than the shipyard's 3-wide footprint, so no
    # single substrip can EVER fit one alone -- only the gate below (area, not width)
    # needs an explicit fixture check.
    assert max(z["area"] for zid, z in zones.items() if zid) >= WT._BORDER_ZONE_MIN_AREA, (
        "fixture assumption broke: at least one lm_b substrip must clear the "
        "sliver-zone gate, or the whole shore would be skipped for an unrelated reason")

    return W, H, grid, zones, lm_b


def test_seaport_placement_analyzes_the_whole_shore_not_one_zone_at_a_time():
    """s10 diagnosis (2026-09): a shore split across several land zones (none wide
    enough alone to fit a shipyard's 3-tile-wide footprint) used to get ZERO seaports,
    even though the shore as a whole plainly has room -- the old code tried each
    bordering zone's own narrow slice in isolation and gave up. Fixed: candidates are
    drawn from the whole shore's near-coastal expansion, spanning every zone it
    touches."""
    from vcmi_mapgen.steps.gameplay import water as WT
    from vcmi_mapgen.ontology import Ontology

    W, H, grid, zones, lm_b = _two_islands_one_split_thin()
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    placed_in_lm_b = [o for o in objs if (o["x"], o["y"]) in lm_b]
    assert placed_in_lm_b, (
        "the second shore (split across many thin zones) got no seaport at all")


def test_seaport_never_fully_blocks_an_existing_structures_front_row():
    """s8-z1 diagnosis (2026-09): a seaport landed squarely in an arena's own front
    row (the row directly below its footprint -- the only geometrically-unobstructed
    approach every multi-row structure mask in this ontology has), fully sealing off
    the arena. Seaports are placed AFTER all per-zone gameplay structures (see
    GameplayStep._run_level_gameplay's "Pass 1... Seaport placement" ordering), so
    nothing stopped a later seaport from claiming an earlier structure's approach.
    Fixture: an 8x4 island with one extra land tile so a seaport CAN anchor with its
    blocking row exactly on a pre-placed arena's front row -- with seed=3 the old code
    reliably picks that exact anchor."""
    from vcmi_mapgen.steps.gameplay import water as WT
    from vcmi_mapgen.ontology import Ontology
    from vcmi_mapgen.kit import objects as OR

    WATER, LAND = 8, 2
    W, H = 20, 20
    grid = [[WATER for _ in range(W)] for _ in range(H)]
    for y in range(4):
        for x in range(8):
            grid[y][x] = LAND
    grid[4][2] = LAND   # extra approach tile: makes the front-row anchor geometrically valid
    zone_tiles = {(x, y) for x in range(8) for y in range(4)} | {(2, 4)}
    zones = {0: {"terrain_type": 2, "tiles_set": zone_tiles, "area": len(zone_tiles),
                "centroid": (4, 2)}}
    arena = {"x": 3, "y": 2, "l": 0, "purpose": "STAT_PERMANENT", "type": "arena",
            "subtype": "object", "mask": ["VVV", "BBB", "BXB"],
            "template": {"mask": ["VVV", "BBB", "BXB"]}}
    front = OR.front_tiles(arena["mask"], arena["x"], arena["y"])
    assert front == {(1, 3), (2, 3), (3, 3)}, "fixture assumption broke: unexpected front tiles"

    objs = WT._ensure_water_seaports(W, H, grid, zones, [arena], seed=3, ontology=Ontology())
    for o in objs:
        blk = {(cx, cy) for cx, cy, b in OR.mask_cells(o["mask"], o["x"], o["y"]) if b}
        assert not front <= blk, (
            f"seaport at ({o['x']}, {o['y']}) consumes the arena's entire front row {front}")


def test_seaport_spacing_is_30_tiles():
    from vcmi_mapgen.steps.gameplay import water as WT
    assert WT._SEAPORT_SPACING_SQ == 30 * 30, (
        f"seaports must be spaced >= 30 tiles apart, got sqrt({WT._SEAPORT_SPACING_SQ})")


def test_ensure_water_seaports_places_at_least_one():
    from vcmi_mapgen.ontology import Ontology

    WT, W, H, grid, zones = _water_and_land_zone()
    objs = WT._ensure_water_seaports(W, H, grid, zones, [], seed=2, ontology=Ontology())
    assert objs, "a land zone bordering a >= _WATER_BODY_MIN water body must get a seaport"


def test_seaport_rng_seed_is_not_derived_from_builtin_hash(monkeypatch):
    """_try_place used to seed its RNG with `seed ^ hash(label) ^ 0x53A9`. Python salts
    str hash() per-process (PYTHONHASHSEED), so the SAME map seed could place seaports in
    different spots on different process launches — a determinism break the project's
    seed contract (AGENTS.md: "the terrain generator is seeded") rules out. Regression for
    the bug fixed by seeding from zlib.crc32(label.encode()) instead: rather than guess the
    exact label strings _place_for_zone builds (they depend on which water-tile/zone-id the
    map happens to pick), this wraps the real zlib.crc32 and random.Random to observe what
    the code actually feeds each, and cross-checks the two — robust to geometry, and it
    fails immediately if the code reverts to hash(label) (crc32 would simply never fire)."""
    from vcmi_mapgen.ontology import Ontology
    from vcmi_mapgen.steps.gameplay import water as WT

    WT_module = WT.__name__  # "vcmi_mapgen.steps.gameplay.water"
    import sys
    wt_mod = sys.modules[WT_module]

    WT_obj, W, H, grid, zones = _water_and_land_zone()

    crc_calls = []
    real_crc32 = zlib.crc32

    def recording_crc32(data, *a):
        result = real_crc32(data, *a)
        crc_calls.append(result)
        return result

    monkeypatch.setattr(wt_mod.zlib, "crc32", recording_crc32)

    seeds_seen = []
    real_random_cls = random.Random

    class RecordingRandom(real_random_cls):
        def __init__(self, seed_arg=None):
            seeds_seen.append(seed_arg)
            super().__init__(seed_arg)

    monkeypatch.setattr(random, "Random", RecordingRandom)

    map_seed = 2
    WT_obj._ensure_water_seaports(W, H, grid, zones, [], seed=map_seed, ontology=Ontology())

    assert crc_calls, (
        "_ensure_water_seaports never called zlib.crc32 — did the seaport RNG regress "
        "back to the process-salted hash(label)?"
    )
    derived_seeds = {map_seed ^ crc ^ 0x53A9 for crc in crc_calls}
    assert derived_seeds & set(seeds_seen), (
        f"none of the crc32-derived seeds {derived_seeds} were actually used to seed a "
        f"random.Random() (saw {seeds_seen}) — crc32 is computed but not wired into the RNG"
    )


def test_place_water_never_places_a_guard():
    """Sea/water bodies get no monster of their own -- a GUARD only ever gates a mine, a
    loot-zone/portal-rescue access object, or a pocket mouth (user-mandated placement
    order: outside those three, no monster). Sampled across many seeds since GUARD is a
    probabilistic pick among WATER_PURPOSES, not a guaranteed-every-call roll."""
    import os
    import pytest
    from vcmi_mapgen.steps.gameplay import mines as PG
    from vcmi_mapgen.steps.gameplay import water as WT

    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(30) for y in range(24)}
    zones = {1: {"tiles_set": sorted(ts), "centroid": (14.5, 11.5), "area": len(ts),
                 "terrain_type": 8}}
    objs = []
    for seed in range(1, 30):
        objs += WT.place_water(ts, zones, 1, seed=seed)
    assert objs, "fixture assumption broke: expected some water objects across 30 seeds"
    assert not any(o.get("purpose") == "GUARD" for o in objs), (
        "place_water must never place a GUARD-purpose object")
