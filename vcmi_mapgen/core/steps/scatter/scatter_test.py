"""Reliability tests for steps.scatter.scatter (unguarded resource piles)."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.scatter import scatter as SC


def test_place_scatter_handles_a_zone_with_no_reachable_open_tile(catalog: Catalog) -> None:
    """A zone whose whole tile set is already occupied by gameplay (open_set empty) still
    has a nonzero resource-pile quota drawn from its raw area — scatter()'s candidate list
    (built from `reach`, derived from `open_set`) then ends up empty, and
    `rng.choices(cands, weights=weights, k=...)` raises IndexError on an empty
    cum_weights. Both the legacy and current pipeline crashed identically here (a real,
    pre-existing, seed/refactor-independent bug); regression for the fix that returns
    early when there are no candidates instead of calling rng.choices()."""
    ts = {(x, y) for x in range(30) for y in range(24)}
    zones = {
        1: Zone(
            terrain_type=Terrain.GRASS,
            area=len(ts),
            centroid=(14.5, 11.5),
            tiles=sorted(ts),
            tiles_set=frozenset(ts),
        )
    }
    objs, used, reach = SC.place_scatter(
        catalog,
        SC.ScatterZone(ts, zones, 1, "grass", open_set=set(), prot=set()),
        SC.ScatterConfig(seed=3, bounds=(30, 24)),
    )
    assert objs == []
    assert used == set()
    assert reach == set()
