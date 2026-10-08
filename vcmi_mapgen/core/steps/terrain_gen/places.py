"""The place-first terrain model (map-math 4): the surface is a place graph laid out on land,
each place base-coated with its dominant terrain, then painted with transition bands,
accents and texture. The underground keeps the macro path."""

import collections
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import ENTRANCE_W, plan_passages
from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.paint import read_paint
from vcmi_mapgen.core.reading.palette import palette_regions, same_share
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.border_kinds import draw_kinds
from vcmi_mapgen.core.steps.terrain_gen.coastline import SurfaceForm
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import carve_gate_sites, gate_anchor_points
from vcmi_mapgen.core.steps.terrain_gen.identity import (
    Palette,
    assign_dominants,
    town_terrains,
)
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.paint import paint_places, paint_priors
from vcmi_mapgen.core.steps.terrain_gen.palette import draw_palette
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph
from vcmi_mapgen.core.steps.terrain_gen.place_map import (
    flood_places,
    front_cells,
    label_adjacency,
    reconcile_places,
)
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlaceMap, PlannedPlace
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import (
    draw_doors,
    draw_partition,
    group_neutral,
    islanded,
    settle,
    stranded,
    territory_plan,
    wall_kinds,
)

UNDERGROUND_SALT = 0x51E9
UNDERGROUND_ENTRANCE_W = 1
BARRIERS = frozenset((Terrain.WATER.value, Terrain.ROCK.value))
MAX_BRIDGE_ROUNDS = 8


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
    catalog: Catalog, form: SurfaceForm, priors: Priors, seed: int, options: TerrainOptions
) -> tuple[list[list[Terrain]], LevelPlaces, tuple[str, ...]]:
    """The painted surface, its place map with its bands, and lines on how the layout and
    the palette went."""
    macro = priors.terrain[0].macro
    stats = priors.places[0]
    coastline = form.form(priors, seed, options)
    graph, layout = coastline.graph, coastline.layout
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
    spread = priors.territories.get(0, TerritoryStats())
    plan = bordered(reconcile_places(grid, plan_of(graph, layout, dominants)), stats, spread, seed)
    painted = paint_places(
        grid,
        plan,
        paint_priors(stats, priors.terrain[0].markov_places),
        seed,
        catalog.thin_terrains(),
    )
    plan = replace(plan, bands=painted.bands)
    lines = (
        line,
        *coastline.log,
        palette_line(k, painted.grid, plan),
        border_line(plan),
        territory_line(plan),
    )
    return painted.grid, plan, lines


def bordered(
    plan: LevelPlaces, stats: PlaceStats, spread: TerritoryStats, seed: int
) -> LevelPlaces:
    """``plan`` split into territories drawn on its planned adjacency, with the kind of
    every inner pair drawn from the corpus table, a door on each border the territories
    need, every other territory border walled, and the passages across them."""
    roles = {p: place.role for p, place in plan.places.items()}
    owners = [plan.places[p].owner for p in sorted(plan.places)]
    drawn = draw_partition(
        owners,
        plan.adjacency,
        spread.player_zones,
        spread.neutral_zones,
        stream(seed, "territories"),
    )
    realised = label_adjacency(plan.label)
    territory, lords = settle(drawn, owners, realised)
    inner = [e for e in sorted(realised) if territory[e[0]] == territory[e[1]]]
    drawn_kinds = draw_kinds(roles, inner, plan.adjacency, stats.adjacency, stream(seed, "borders"))
    doors = draw_doors(
        territory, realised, plan.adjacency, spread.pair_doors, stream(seed, "doors")
    )
    kinds = wall_kinds(territory, realised, drawn_kinds, doors)
    return walled(plan, (territory, lords), kinds, doors, ENTRANCE_W)


def walled(
    plan: LevelPlaces,
    partition: tuple[Sequence[int], Sequence[int | None]],
    kinds: Mapping[tuple[int, int], AdjacencyKind],
    doors: Mapping[tuple[int, int], int],
    gated_w: int,
) -> LevelPlaces:
    """``plan`` with its territories, the kind of every realised pair, and the passages
    across them: each door ``DOOR_W`` wide and each other gated passage ``gated_w``."""
    territory, lords = partition
    passages = plan_passages(plan.label, kinds, doors, gated_w)
    return replace(
        plan,
        kinds=kinds,
        passages=passages,
        territories=territory_plan(territory, lords, doors, passages),
    )


def underground_places(
    grid: Sequence[Sequence[Terrain]], spread: TerritoryStats, seed: int
) -> LevelPlaces:
    """The underground's places, one per same-terrain region, grouped on the borders they
    share into neutral territories sized from the corpus spread. Inner borders stay gated,
    each passage ``UNDERGROUND_ENTRANCE_W`` wide, and the territories meet at doors."""
    plan = flood_places(grid, UNDERGROUND_ENTRANCE_W)
    realised = label_adjacency(plan.label)
    owners = [None] * len(plan.places)
    drawn = [0] * len(plan.places)
    rng = stream(seed, "territories", 1)
    for t, group in enumerate(
        group_neutral(range(len(owners)), realised, spread.neutral_zones, rng)
    ):
        for p in group:
            drawn[p] = t
    territory, lords = settle(drawn, owners, realised)
    doors = draw_doors(territory, realised, realised, spread.pair_doors, stream(seed, "doors", 1))
    kinds = wall_kinds(territory, realised, dict.fromkeys(realised, AdjacencyKind.GATED), doors)
    return walled(plan, (territory, lords), kinds, doors, UNDERGROUND_ENTRANCE_W)


def territory_line(plan: LevelPlaces, name: str = "territories") -> str:
    """How many territories each kind of owner holds, their doors, the homes no door opens
    on a land border, and the homes water parts from every other territory."""
    tp = plan.territories
    players = sum(o is not None for o in tp.owners)
    walls = sum(
        1
        for (a, b), kind in plan.kinds.items()
        if kind == AdjacencyKind.CLOSED and tp.zones[a] != tp.zones[b]
    )
    realised = label_adjacency(plan.label)
    lost, islands = stranded(tp, realised), islanded(tp, realised)
    return (
        f"  {name}: {len(tp.owners)}, {players} player, {len(tp.owners) - players} "
        + f"neutral, {len(tp.doors)} doors, {walls} walled borders"
        + (f", stranded players {lost}" if lost else "")
        + (f", players alone on their land {islands}" if islands else "")
    )


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
    """A place-first surface on the land its surface form gives, and today's underground."""

    def __init__(self, form: SurfaceForm) -> None:
        self.form: SurfaceForm = form

    def draw(
        self, catalog: Catalog, priors: Priors, seed: int, options: TerrainOptions
    ) -> TerrainDraw:
        grid0, plan0, lines = surface(catalog, self.form, priors, seed, options)
        if not options.subterrain:
            return TerrainDraw({0: grid0}, frozenset(), PlaceMap({0: plan0}), lines)
        raw1, tunnels = underground(priors.terrain[1], grid0, seed, options.size)
        grid1 = despeckle(raw1, catalog.thin_terrains(), tunnels)
        plan1 = underground_places(grid1, priors.territories.get(1, TerritoryStats()), seed)
        protect = tunnels - front_cells(plan1.label)
        lines = (*lines, territory_line(plan1, "underground territories"))
        return TerrainDraw({0: grid0, 1: grid1}, protect, PlaceMap({0: plan0, 1: plan1}), lines)
