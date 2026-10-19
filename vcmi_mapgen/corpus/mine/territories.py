"""Mine the corpus territory spread of each level through the shared territory reader."""

from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.territories import (
    TerritoryCount,
    TerritoryPlan,
    TerritorySite,
    TerritoryStats,
)
from vcmi_mapgen.core.reading.ground import TownKey, purpose_of, read_ground
from vcmi_mapgen.core.reading.territories import (
    NONE,
    Territories,
    TerritoryReading,
    read_territories,
    territory_reading,
)
from vcmi_mapgen.core.reading.value import PURPOSE_VALUE, ValueTable, value_of


def plan_sites(read: Territories, size: int) -> tuple[TerritorySite, ...] | None:
    """The sites of the territories ``read`` found on a map ``size`` tiles wide: each one's
    centroid over the side, its share of the territory area and its player. None when a
    territory has several players, since a plan seats one player per territory."""
    if any(len(t.owners) > 1 for t in read.territories):
        return None
    n = len(read.territories)
    xs, ys, tiles = [0.0] * n, [0.0] * n, [0] * n
    for y, row in enumerate(read.labels):
        for x, t in enumerate(row):
            if t != NONE:
                xs[t] += (x + 0.5) / size
                ys[t] += (y + 0.5) / size
                tiles[t] += 1
    total = sum(t.area for t in read.territories)
    return tuple(
        TerritorySite(
            xs[i] / tiles[i], ys[i] / tiles[i], t.area / total, t.owners[0] if t.owners else None
        )
        for i, t in enumerate(read.territories)
        if tiles[i] > 0
    )


def mine_territories(
    catalog: Catalog,
    level: int,
    maps: Sequence[MapState],
    owners: Sequence[Mapping[TownKey, int]],
    players: Sequence[int],
) -> TerritoryStats:
    """The territories of ``level`` read on every map that has it, pooled, with the door
    levels of each map that has doors kept apart, and the territory count of each map that
    has territories beside its player count, land tiles, territory areas and prizes. A
    player territory several players share counts as an equal part for each. A prize is a
    town or an object of the level worth at least a mine."""
    table = ValueTable.of(catalog)
    mine = PURPOSE_VALUE[Purpose.MINE]
    readings: list[TerritoryReading] = []
    counts: list[TerritoryCount] = []
    plans: list[TerritoryPlan] = []
    for state, own, n in zip(maps, owners, players, strict=True):
        read = read_territories(catalog, state, level, own)
        ground = read_ground(catalog, state, level)
        if read is None or ground is None:
            continue
        reading = territory_reading(read)
        readings.append(reading)
        if reading.territories:
            area = sum(reading.player_areas) + sum(reading.neutral_areas)
            homes = tuple(t.area // len(t.owners) for t in read.territories for _ in t.owners)
            prizes = sum(
                1
                for o in state.objs
                if o.level == level
                and (purpose_of(catalog, o) == Purpose.TOWN or value_of(catalog, table, o) >= mine)
            )
            count = TerritoryCount(n, len(ground.land), reading.territories, homes, area, prizes)
            counts.append(count)
            sites = plan_sites(read, state.size)
            if sites is not None:
                plans.append(TerritoryPlan(count, sites))
    return TerritoryStats(
        pair_doors=tuple(n for r in readings for n in r.pair_doors),
        player_doors_by_map=tuple(r.player_door_levels for r in readings if r.player_door_levels),
        neutral_doors_by_map=tuple(
            r.neutral_door_levels for r in readings if r.neutral_door_levels
        ),
        counts_by_map=tuple(counts),
        plans_by_map=tuple(plans),
    )
