"""The surface form role: where the surface is land and where it is water, with the places
laid out on that land. The noise form is the original variant."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import gate_anchor_points, gate_site_tiles
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout, lay_out
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph, draw_graph
from vcmi_mapgen.core.steps.terrain_gen.streams import stream


@dataclass(frozen=True, slots=True)
class Coastline:
    """The place graph and its layout, with water labelled -1, and the lines the form
    reports."""

    graph: PlaceGraph
    layout: Layout
    log: tuple[str, ...] = ()


class SurfaceForm(Protocol):
    def form(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        """The surface's places on its land, the same for the same seed."""
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
        anchors = gate_anchor_points(options.size, options.size, seed)
        for x, y in gate_site_tiles(anchors, options.size):
            land[y][x] = True
    return land


class NoiseForm:
    """A noise land mask first, then the place graph and its layout on that land."""

    def form(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        stats = priors.places[0]
        land = ground(priors.terrain[0].macro.barrier_fracs, seed, options)
        n_land = sum(v for row in land for v in row)
        graph = draw_graph(stats, options.players, n_land, stream(seed, "places"))
        return Coastline(graph, lay_out(land, graph, target_gap(stats), stream(seed, "layout")))
