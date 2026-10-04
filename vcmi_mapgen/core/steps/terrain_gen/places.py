"""The place-first terrain model (map-math 4): the surface is a place graph laid out on land,
each place base-coated with its dominant terrain, then painted with transition bands,
accents and texture. The underground keeps the macro path."""

import collections
import statistics
from collections.abc import Collection, Sequence
from dataclasses import replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import plan_passages
from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.paint import read_paint
from vcmi_mapgen.core.reading.palette import palette_regions, same_share
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.border_kinds import draw_kinds
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import (
    carve_gate_sites,
    gate_anchor_points,
    gate_site_tiles,
)
from vcmi_mapgen.core.steps.terrain_gen.identity import (
    Palette,
    assign_dominants,
    town_terrains,
)
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout, lay_out
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.paint import paint_places, paint_priors
from vcmi_mapgen.core.steps.terrain_gen.palette import draw_palette
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph, draw_graph
from vcmi_mapgen.core.steps.terrain_gen.place_map import (
    flood_places,
    front_cells,
    label_adjacency,
    reconcile_places,
)
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlaceMap, PlannedPlace
from vcmi_mapgen.core.steps.terrain_gen.streams import stream

UNDERGROUND_SALT = 0x51E9
UNDERGROUND_ENTRANCE_W = 1
BARRIERS = frozenset((Terrain.WATER.value, Terrain.ROCK.value))
MAX_BRIDGE_ROUNDS = 8


def ground(macro_fracs: Sequence[float], seed: int, options: TerrainOptions) -> list[list[bool]]:
    """The surface land mask from today's water model, with every gate site made land when
    the map has an underground."""
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


def target_gap(stats: PlaceStats) -> float:
    """The lower quartile of the corpus home separation, 0 without two samples."""
    seps = stats.home_separation
    return statistics.quantiles(seps, n=4)[0] if len(seps) >= 2 else 0.0


def plan_of(graph: PlaceGraph, layout: Layout, dominants: Sequence[Terrain]) -> LevelPlaces:
    """The planned place map: the graph's places, then a pocket per land mass no anchor
    reached, each with its dominant terrain, and the graph's edges."""
    extra = layout.places - len(graph.roles)
    roles = (*graph.roles, *([PlaceRole.POCKET] * extra))
    owners = (*graph.owners, *([None] * extra))
    places = {i: PlannedPlace(roles[i], owners[i], dominants[i]) for i in range(layout.places)}
    return LevelPlaces(layout.label, places, graph.edges)


def paint(label: Sequence[Sequence[int]], dominants: Sequence[Terrain]) -> list[list[int]]:
    """Each land tile in its place's dominant terrain, every other tile water."""
    return [[dominants[z].value if z >= 0 else Terrain.WATER.value for z in row] for row in label]


def bridge_pinches(ids: list[list[int]]) -> bool:
    """Make one water tile of every 2x2 square whose land touches only across the diagonal
    into the terrain of the land beside it, so a hero walks where the eye sees a coast.
    Returns whether any tile changed."""
    changed = False
    for y in range(len(ids) - 1):
        top, low = ids[y], ids[y + 1]
        for x in range(len(top) - 1):
            land = [t not in BARRIERS for t in (top[x], top[x + 1], low[x], low[x + 1])]
            if land == [True, False, False, True]:
                top[x + 1] = top[x]
                changed = True
            elif land == [False, True, True, False]:
                top[x] = top[x + 1]
                changed = True
    return changed


def coast(ids: list[list[int]], thin: Collection[Terrain]) -> list[list[Terrain]]:
    """The despeckled grid with every diagonal-only land contact bridged, despeckled again
    after each round of bridges."""
    grid = despeckle(ids, thin)
    for _ in range(MAX_BRIDGE_ROUNDS):
        work = [[t.value for t in row] for row in grid]
        if not bridge_pinches(work):
            break
        grid = despeckle(work, thin)
    return grid


def surface(
    catalog: Catalog, priors: Priors, seed: int, options: TerrainOptions
) -> tuple[list[list[Terrain]], LevelPlaces, tuple[str, ...]]:
    """The painted surface, its place map with its bands, and lines on how the layout and
    the palette went."""
    macro = priors.terrain[0].macro
    stats = priors.places[0]
    land = ground(macro.barrier_fracs, seed, options)
    n_land = sum(v for row in land for v in row)
    graph = draw_graph(stats, options.players, n_land, stream(seed, "places"))
    layout = lay_out(land, graph, target_gap(stats), stream(seed, "layout"))
    roles = [*graph.roles, *([PlaceRole.POCKET] * (layout.places - len(graph.roles)))]
    adjacency = label_adjacency(layout.label)
    k, groups = draw_palette(
        stats.palette_counts, macro.areas, layout.label, adjacency, stream(seed, "palette")
    )
    dominants = assign_dominants(
        Palette(roles, adjacency, groups),
        (stats, macro),
        town_terrains(catalog),
        stream(seed, "identity"),
    )
    grid = coast(paint(layout.label, dominants), catalog.thin_terrains())
    line = (
        f"  places: {len(graph.roles)} planned, {layout.places} grown, "
        + f"{len(layout.missing)} planned borders missing, home gap {layout.home_gap:.2f}"
    )
    plan = bordered(reconcile_places(grid, plan_of(graph, layout, dominants)), stats, seed)
    painted = paint_places(
        grid,
        plan,
        paint_priors(stats, priors.terrain[0].markov_places),
        seed,
        catalog.thin_terrains(),
    )
    plan = replace(plan, bands=painted.bands)
    return painted.grid, plan, (line, palette_line(k, painted.grid, plan), border_line(plan))


def bordered(plan: LevelPlaces, stats: PlaceStats, seed: int) -> LevelPlaces:
    """``plan`` with the kind of every realised pair drawn from the corpus table and the
    passages across them."""
    roles = {p: place.role for p, place in plan.places.items()}
    kinds = draw_kinds(
        roles, label_adjacency(plan.label), plan.adjacency, stats.adjacency, stream(seed, "borders")
    )
    return replace(plan, kinds=kinds, passages=plan_passages(plan.label, kinds))


def border_line(plan: LevelPlaces) -> str:
    """How many realised borders drew each kind, and how many entrances they hold."""
    count = collections.Counter(plan.kinds.values())
    entrances = sum(len(e) for e in plan.passages.entrances.values()) // 2
    return (
        f"  borders: {len(plan.kinds)} realised, {count[AdjacencyKind.CLOSED]} closed, "
        + f"{count[AdjacencyKind.GATED]} gated, {count[AdjacencyKind.OPEN]} open, "
        + f"{entrances} entrances"
    )


def palette_line(k: int, grid: Sequence[Sequence[Terrain]], plan: LevelPlaces) -> str:
    """The drawn palette region count, then the realised region count, the share of place
    borders between places of one dominant and the raw-cut share, read on the planned
    places."""
    dom = {p: pl.dominant for p, pl in plan.places.items()}
    adj = label_adjacency(plan.label)
    cut = read_paint(grid, plan.label, dom, plan.bands)
    return (
        f"  palette: {k} regions drawn, {palette_regions(dom, adj)} realised, "
        + f"same share {same_share(dom, adj) or 0.0:.2f}, "
        + f"raw cut {cut.raw_cut / max(1, cut.border):.3f}"
    )


def underground(
    priors: TerrainPriors, surface_grid: Sequence[Sequence[Terrain]], seed: int, size: int
) -> tuple[list[list[int]], frozenset[Tile]]:
    """Today's underground with its gate sites carved, and its tunnel cells. The surface
    copy the carving paints is thrown away."""
    protect: set[Tile] = set()
    grid1 = MTOPO.generate(
        size, seed ^ UNDERGROUND_SALT, priors, MTOPO.MacroOptions(level=1), protect_out=protect
    )
    scratch = [[t.value for t in row] for row in surface_grid]
    protect |= carve_gate_sites(scratch, grid1, gate_anchor_points(size, size, seed), seed)
    return grid1, frozenset(protect)


class PlacesTerrain:
    """A place-first surface and today's underground."""

    def draw(
        self, catalog: Catalog, priors: Priors, seed: int, options: TerrainOptions
    ) -> TerrainDraw:
        grid0, plan0, lines = surface(catalog, priors, seed, options)
        if not options.subterrain:
            return TerrainDraw({0: grid0}, frozenset(), PlaceMap({0: plan0}), lines)
        raw1, tunnels = underground(priors.terrain[1], grid0, seed, options.size)
        grid1 = despeckle(raw1, catalog.thin_terrains(), tunnels)
        plan1 = flood_places(grid1, UNDERGROUND_ENTRANCE_W)
        protect = tunnels - front_cells(plan1.label)
        return TerrainDraw({0: grid0, 1: grid1}, protect, PlaceMap({0: plan0, 1: plan1}), lines)
