"""Reliability tests for kit.topology (gate bands, entrance planning, pocket geometry)."""

from vcmi_mapgen.kit import topology as ZF


def test_zone_gate_bands_wide_and_protected():
    """Zone gates are corpus-wide BANDS of the contact front, and the protected web keeps
    the whole band vegetation-free — borders must never collapse to a 1-tile corridor."""
    # two 12x10 zones side by side: the contact front is the full 10-tile column
    ts1 = {(x, y) for x in range(12) for y in range(10)}
    ts2 = {(x, y) for x in range(12, 24) for y in range(10)}
    zones = {1: {"tiles_set": sorted(ts1), "centroid": (5.5, 4.5), "area": 120,
                 "terrain_type": 2},
             2: {"tiles_set": sorted(ts2), "centroid": (17.5, 4.5), "area": 120,
                 "terrain_type": 3}}
    bands = ZF._zone_gate_bands(ts1, zones, 1, open_frac=0.5)
    fronts = [(rep, band) for rep, band in bands if all(t[0] == 11 for t in band)]
    assert fronts, "zone 1 must have a band on its contact front with zone 2"
    rep, band = fronts[0]
    assert len(band) >= 5, f"open_frac=0.5 of a 10-tile front is 5 tiles, got {len(band)}"
    assert rep in band and all(t in ts1 for t in band)
    # a tiny open_frac still keeps the minimum width
    bands_min = ZF._zone_gate_bands(ts1, zones, 1, open_frac=0.01)
    _rep, band_min = [(r, b) for r, b in bands_min if all(t[0] == 11 for t in b)][0]
    assert len(band_min) >= 3, "bands never collapse below min_w"
    # determinism
    assert ZF._zone_gate_bands(ts1, zones, 1, open_frac=0.5) == bands


def test_plan_entrances_aligned_and_few():
    """Entrance plan: 1 crossing for a short front, 2 for a long one, both sides' bands
    aligned (4-adjacent across the border), <=ENTRANCE_W tiles per side, deterministic."""
    # short front: two 12x10 zones -> exactly ONE entrance for the pair
    ts1 = {(x, y) for x in range(12) for y in range(10)}
    ts2 = {(x, y) for x in range(12, 24) for y in range(10)}
    zones = {1: {"tiles_set": sorted(ts1), "centroid": (5.5, 4.5), "area": 120,
                 "terrain_type": 2},
             2: {"tiles_set": sorted(ts2), "centroid": (17.5, 4.5), "area": 120,
                 "terrain_type": 3}}
    plan = ZF.plan_entrances(zones)
    assert len(plan[1]) == 1 and len(plan[2]) == 1, "10-tile front gets a single entrance"
    rep1, band1, other1 = plan[1][0]
    rep2, band2, other2 = plan[2][0]
    assert other1 == 2 and other2 == 1
    assert rep1 in band1 and band1 <= ts1 and len(band1) <= ZF.ENTRANCE_W
    assert rep2 in band2 and band2 <= ts2 and len(band2) <= ZF.ENTRANCE_W
    assert abs(rep1[0] - rep2[0]) + abs(rep1[1] - rep2[1]) == 1, \
        "the two sides' reps must be 4-adjacent (aligned crossing)"
    assert plan == ZF.plan_entrances(zones), "planner must be deterministic"

    # long front: 30-tile contact column -> two entrances, far apart
    ts3 = {(x, y) for x in range(12) for y in range(30)}
    ts4 = {(x, y) for x in range(12, 24) for y in range(30)}
    zl = {1: {"tiles_set": sorted(ts3), "centroid": (5.5, 14.5), "area": 360,
              "terrain_type": 2},
          2: {"tiles_set": sorted(ts4), "centroid": (17.5, 14.5), "area": 360,
              "terrain_type": 3}}
    plan2 = ZF.plan_entrances(zl)
    assert len(plan2[1]) == ZF.MAX_ENTRANCES, "30-tile front earns a second entrance"
    (ra, _, _), (rb, _, _) = plan2[1]
    assert max(abs(ra[0] - rb[0]), abs(ra[1] - rb[1])) >= ZF.MIN_ENTRANCE_SEP, \
        "the two entrances of one pair must not crowd each other"


def test_pocket_depths_increase_from_mouth_to_deepest_tile():
    """A straight 4-tile corridor pocket: depth must increase monotonically away from
    the mouth, and every pocket tile must get a depth (none left unreached)."""
    pocket = frozenset({(1, 0), (2, 0), (3, 0), (4, 0)})
    mouth = frozenset({(0, 0)})  # just outside the pocket, 8-adjacent to (1, 0)
    depths = ZF.pocket_depths(pocket, mouth)
    assert set(depths) == pocket
    assert depths[(1, 0)] == 0
    assert depths[(2, 0)] == 1
    assert depths[(3, 0)] == 2
    assert depths[(4, 0)] == 3


def test_pocket_depths_takes_the_shortest_path_when_the_pocket_branches():
    """(2, 0) is reachable from the mouth via BOTH (1, 0) and (1, 1) at the same
    distance, and (3, 0) is one step deeper than either -- every tile gets its
    shortest 8-connected distance from the mouth, regardless of how many
    predecessors it has."""
    pocket = frozenset({(1, 0), (1, 1), (2, 0), (3, 0)})
    mouth = frozenset({(0, 0)})
    depths = ZF.pocket_depths(pocket, mouth)
    assert depths[(1, 0)] == 0   # 8-adjacent to mouth
    assert depths[(1, 1)] == 0   # also 8-adjacent to mouth
    assert depths[(2, 0)] == 1   # one step from either (1,0) or (1,1)
    assert depths[(3, 0)] == 2   # one step deeper still


def _open_field_with_room(room_tiles, mouth=((5, 4), (6, 4)), field_w=15, field_h=4):
    """A big open field (rows 0..field_h-1) connected to `room_tiles` ONLY through the
    two 4-connected `mouth` tiles -- everything else around the room is a wall (simply
    absent from `reach`)."""
    from vcmi_mapgen.kit import topology as TP
    field = {(x, y) for x in range(field_w) for y in range(field_h)}
    reach = field | set(mouth) | set(room_tiles)
    return TP, reach


def _top_pocket(TP, reach):
    """find_pockets alone can return several overlapping raw candidates for the SAME
    physical nook (e.g. the true outer doorway, and an inner partition of the room that
    is technically also a valid-but-smaller 2-tile doorway) -- `steps.repair.caches.
    _dedupe_pockets` blob-merges those and keeps the best one, exactly as the real
    pipeline always calls it. Asserts exactly one physical nook was found and returns
    its (guard_tile, pocket, mouth_fs)."""
    from vcmi_mapgen.steps.repair.caches import _dedupe_pockets
    raw = TP.find_pockets(reach)
    blobs = _dedupe_pockets(raw, reach)
    assert len(blobs) == 1, f"expected exactly one physical nook, got {len(blobs)}"
    return blobs[0][0]   # best candidate in the blob


def test_find_pockets_detects_the_two_tile_doorway_cavity():
    """A 4-tile room behind an EXACT 2-tile, 4-connected doorway is found, with the
    mouth being exactly those two doorway tiles."""
    room = {(5, 5), (6, 5), (5, 6), (6, 6)}
    TP, reach = _open_field_with_room(room)
    _guard_tile, pocket, mouth_fs = _top_pocket(TP, reach)
    assert pocket == frozenset(room)
    assert mouth_fs == frozenset({(5, 4), (6, 4)})


def test_find_pockets_mouth_is_always_exactly_two_tiles():
    room = {(5, 5), (6, 5)}
    TP, reach = _open_field_with_room(room)
    _guard_tile, _pocket, mouth_fs = _top_pocket(TP, reach)
    assert len(mouth_fs) == 2
    m1, m2 = sorted(mouth_fs)
    assert max(abs(m1[0] - m2[0]), abs(m1[1] - m2[1])) == 1
    assert m1[0] == m2[0] or m1[1] == m2[1]   # 4-connected, not diagonal


def test_find_pockets_rejects_a_cavity_over_ten_tiles():
    """A room of 11 tiles behind a 2-tile doorway must NOT be reported -- the cavity
    exceeds the user-mandated 1..10 tile window. (Small inner-partition candidates may
    still be found -- see _top_pocket -- but none may reach the full 11-tile room.)"""
    room = {(x, y) for x in range(5, 9) for y in range(5, 8)}   # 4x3 = 12 tiles
    room = set(list(room)[:11])   # trim to exactly 11 for an unambiguous over-the-line case
    TP, reach = _open_field_with_room(room)
    pockets = TP.find_pockets(reach)
    assert all(len(pocket) < 11 for pocket, _mouth in pockets.values())


def test_find_pockets_accepts_exactly_ten_tiles():
    room = {(x, y) for x in range(5, 7) for y in range(5, 10)}   # 2x5 = 10 tiles
    TP, reach = _open_field_with_room(room, mouth=((5, 4), (6, 4)))
    _guard_tile, pocket, _mouth = _top_pocket(TP, reach)
    assert len(pocket) == 10


def test_find_pockets_guard_tile_is_one_of_the_mouth_tiles():
    """Both mouth tiles sit within Chebyshev 1 of the reported guard_tile -- a single
    guard standing there has both inside its 3x3 zone of control (the "same monster
    zoc" requirement is automatic for any 4-connected pair, since they're always
    Chebyshev-1 apart)."""
    room = {(5, 5), (6, 5), (5, 6), (6, 6)}
    TP, reach = _open_field_with_room(room)
    guard_tile, _pocket, mouth_fs = _top_pocket(TP, reach)
    assert guard_tile in mouth_fs
    for m in mouth_fs:
        assert max(abs(guard_tile[0] - m[0]), abs(guard_tile[1] - m[1])) <= 1
