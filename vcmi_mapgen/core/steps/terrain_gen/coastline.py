"""The surface form role: where the surface is land before the places grow, and where water
floods once the shapes, the homes and the territories stand. The noise form draws its water
first and floods nothing after."""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import gate_anchor_points, gate_site_tiles
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.streams import stream

type Pair = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Coastline:
    """The land the places grow on, the land count the place count reads, and the lines the
    form reports."""

    land: list[list[bool]]
    planned: int
    log: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Shore:
    """What the flood reads: the grown shapes, the territory of each place, the doors drawn
    on their borders, the wall width between every zone pair of two territories wider than
    one tile, and the tiles that stay land."""

    layout: Layout
    territory: tuple[int, ...]
    doors: frozenset[Pair]
    depths: Mapping[Pair, int]
    keep: frozenset[Tile]


class SurfaceForm(Protocol):
    def land(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        """The surface's land before the places grow, the same for the same seed."""
        ...

    def flood(
        self, shore: Shore, priors: Priors, seed: int, options: TerrainOptions, /
    ) -> tuple[Layout, tuple[str, ...]]:
        """``shore``'s layout with its flooded tiles labelled -1, and the lines the flood
        reports, the same for the same seed."""
        ...


def target_gap(stats: PlaceStats) -> float:
    """The lower quartile of the corpus home separation, 0 without two samples."""
    seps = stats.home_separation
    return statistics.quantiles(seps, n=4)[0] if len(seps) >= 2 else 0.0


def ground(macro_fracs: Sequence[float], seed: int, options: TerrainOptions) -> list[list[bool]]:
    """The surface land mask from the noise water model, with every gate site made land
    when the map has an underground."""
    land = MTOPO.surface_land(
        options.size,
        macro_fracs,
        MTOPO.MacroOptions(water_mode=options.water_mode),
        stream(seed, "ground"),
    )
    if options.subterrain:
        for x, y in gate_tiles(seed, options):
            land[y][x] = True
    return land


def gate_tiles(seed: int, options: TerrainOptions) -> frozenset[Tile]:
    """The gate site tiles of a map with an underground, none without one."""
    if not options.subterrain:
        return frozenset()
    anchors = gate_anchor_points(options.size, options.size, seed)
    return frozenset(gate_site_tiles(anchors, options.size))


class NoiseForm:
    """A noise land mask first, and no flood once the places stand."""

    def land(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        land = ground(priors.terrain[0].macro.barrier_fracs, seed, options)
        return Coastline(land, sum(v for row in land for v in row))

    def flood(
        self, shore: Shore, _priors: Priors, _seed: int, _options: TerrainOptions, /
    ) -> tuple[Layout, tuple[str, ...]]:
        return shore.layout, ()
