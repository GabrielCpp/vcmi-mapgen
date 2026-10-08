"""The segmentation of each despeckled terrain level into one zone per place, with the
tunnel cells, the sliver warnings and the accents of each level."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.grid.segment import ZoneLabel, zones_of_labels
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.reading.paint import Accent, accents
from vcmi_mapgen.core.steps.terrain_gen.result import Accents, PlaceMap, Segmentation

NO_TILES: frozenset[Tile] = frozenset()

MIN_ZONE_AREA = 25
"""A zone smaller than this draws a warning. Hardcoded, not mined."""


def level_protect(level: int, tunnel_protect: frozenset[Tile]) -> frozenset[Tile]:
    """The tunnel cells on ``level``: the underground keeps them, the surface has none."""
    return tunnel_protect if level == 1 else NO_TILES


def sliver_warnings(
    zones: Mapping[int, Zone], level: int, protect: frozenset[Tile] = NO_TILES
) -> list[str]:
    """One warning per zone under ``MIN_ZONE_AREA`` tiles that holds no protected tile."""
    return [
        f"  WARNING: level {level} zone {zid} is very small ({z.area} tiles, "
        + f"terrain {z.terrain_type})"
        for zid, z in zones.items()
        if z.area < MIN_ZONE_AREA and not (z.tiles_set & protect)
    ]


def segment_places(
    terrain: Mapping[int, Sequence[Sequence[Terrain]]],
    places: PlaceMap,
    tunnel_protect: frozenset[Tile],
) -> tuple[Segmentation, list[str]]:
    """Each level's zones, one per place with the place's terrain, its zone label grid, and
    the sliver warnings."""
    zones: dict[int, dict[int, Zone]] = {}
    labels: dict[int, ZoneLabel] = {}
    warnings: list[str] = []
    for level, grid in terrain.items():
        plan = places.levels[level]
        dominant = {pid: place.dominant for pid, place in plan.places.items()}
        zones[level] = zones_of_labels(grid, plan.label, dominant)
        labels[level] = plan.label
        warnings += sliver_warnings(zones[level], level, level_protect(level, tunnel_protect))
    return Segmentation(zones, labels), warnings


def level_accents(terrain: Mapping[int, Sequence[Sequence[Terrain]]], places: PlaceMap) -> Accents:
    """Each level's accent patches, read against its places' dominant terrains."""
    out: dict[int, tuple[Accent, ...]] = {}
    for level, grid in terrain.items():
        plan = places.levels[level]
        dominant = {pid: place.dominant for pid, place in plan.places.items()}
        out[level] = tuple(accents(grid, plan.label, dominant))
    return Accents(out)
