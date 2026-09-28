"""Reliability tests for kit.topology (gate bands, entrance planning)."""

from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.kit import topology as ZF


def _zone(ts: set[Tile], centroid: tuple[float, float], area: int, terrain_type: int) -> Zone:
    return Zone(
        terrain_type=terrain_type,
        area=area,
        centroid=centroid,
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def test_zone_gate_bands_wide_and_protected() -> None:
    """Zone gates are corpus-wide BANDS of the contact front, and the protected web keeps
    the whole band vegetation-free — borders must never collapse to a 1-tile corridor."""
    # two 12x10 zones side by side: the contact front is the full 10-tile column
    ts1 = {(x, y) for x in range(12) for y in range(10)}
    ts2 = {(x, y) for x in range(12, 24) for y in range(10)}
    zones = {
        1: _zone(ts1, (5.5, 4.5), 120, 2),
        2: _zone(ts2, (17.5, 4.5), 120, 3),
    }
    bands = ZF.zone_gate_bands(ts1, zones, 1, open_frac=0.5)
    fronts = [(rep, band) for rep, band in bands if all(t[0] == 11 for t in band)]
    assert fronts, "zone 1 must have a band on its contact front with zone 2"
    rep, band = fronts[0]
    assert len(band) >= 5, f"open_frac=0.5 of a 10-tile front is 5 tiles, got {len(band)}"
    assert rep in band and all(t in ts1 for t in band)
    # a tiny open_frac still keeps the minimum width
    bands_min = ZF.zone_gate_bands(ts1, zones, 1, open_frac=0.01)
    _rep, band_min = next((r, b) for r, b in bands_min if all(t[0] == 11 for t in b))
    assert len(band_min) >= 3, "bands never collapse below min_w"
    # determinism
    assert ZF.zone_gate_bands(ts1, zones, 1, open_frac=0.5) == bands


def test_plan_entrances_aligned_and_few() -> None:
    """Entrance plan: 1 crossing for a short front, 2 for a long one, both sides' bands
    aligned (4-adjacent across the border), <=ENTRANCE_W tiles per side, deterministic."""
    # short front: two 12x10 zones -> exactly ONE entrance for the pair
    ts1 = {(x, y) for x in range(12) for y in range(10)}
    ts2 = {(x, y) for x in range(12, 24) for y in range(10)}
    zones = {
        1: _zone(ts1, (5.5, 4.5), 120, 2),
        2: _zone(ts2, (17.5, 4.5), 120, 3),
    }
    plan = ZF.plan_entrances(zones)
    assert len(plan[1]) == 1 and len(plan[2]) == 1, "10-tile front gets a single entrance"
    rep1, band1, other1 = plan[1][0]
    rep2, band2, other2 = plan[2][0]
    assert other1 == 2 and other2 == 1
    assert rep1 in band1 and band1 <= ts1 and len(band1) <= ZF.ENTRANCE_W
    assert rep2 in band2 and band2 <= ts2 and len(band2) <= ZF.ENTRANCE_W
    assert abs(rep1[0] - rep2[0]) + abs(rep1[1] - rep2[1]) == 1, (
        "the two sides' reps must be 4-adjacent (aligned crossing)"
    )
    assert plan == ZF.plan_entrances(zones), "planner must be deterministic"

    # long front: 30-tile contact column -> two entrances, far apart
    ts3 = {(x, y) for x in range(12) for y in range(30)}
    ts4 = {(x, y) for x in range(12, 24) for y in range(30)}
    zl = {
        1: _zone(ts3, (5.5, 14.5), 360, 2),
        2: _zone(ts4, (17.5, 14.5), 360, 3),
    }
    plan2 = ZF.plan_entrances(zl)
    assert len(plan2[1]) == ZF.MAX_ENTRANCES, "30-tile front earns a second entrance"
    (ra, _, _), (rb, _, _) = plan2[1]
    assert max(abs(ra[0] - rb[0]), abs(ra[1] - rb[1])) >= ZF.MIN_ENTRANCE_SEP, (
        "the two entrances of one pair must not crowd each other"
    )
