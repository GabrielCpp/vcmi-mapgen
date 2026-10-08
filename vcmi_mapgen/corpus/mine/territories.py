"""Mine the corpus territory spread of each level through the shared territory reader."""

from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.ground import TownKey
from vcmi_mapgen.core.reading.territories import read_territories, territory_reading


def mine_territories(
    catalog: Catalog,
    level: int,
    maps: Sequence[MapState],
    owners: Sequence[Mapping[TownKey, int]],
) -> TerritoryStats:
    """The territories of ``level`` read on every map that has it, pooled, with the door
    levels of each map that has doors kept apart."""
    readings = [
        territory_reading(read)
        for state, own in zip(maps, owners, strict=True)
        if (read := read_territories(catalog, state, level, own)) is not None
    ]
    return TerritoryStats(
        player_zones=tuple(n for r in readings for n in r.player_zones),
        neutral_zones=tuple(n for r in readings for n in r.neutral_zones),
        pair_doors=tuple(n for r in readings for n in r.pair_doors),
        player_doors_by_map=tuple(r.player_door_levels for r in readings if r.player_door_levels),
        neutral_doors_by_map=tuple(
            r.neutral_door_levels for r in readings if r.neutral_door_levels
        ),
    )
