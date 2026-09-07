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
