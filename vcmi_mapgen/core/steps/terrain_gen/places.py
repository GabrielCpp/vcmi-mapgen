"""The place-first terrain model (map-math 4): the surface's places grow as shapes on its
land, the homes and the territories stand on them, the water floods, and the roles label
them. Each place is base-coated with its dominant terrain, then painted with transition
bands, accents and texture. The underground keeps the macro path for its caves, and its places
split into territories by the same front as the surface, with no home, the gates between
the levels counted as doors."""

import collections
import random
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.footprint import room_offsets
from vcmi_mapgen.core.planning.entrances import ENTRANCE_W, plan_passages
from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.territories import TerritoryCount, TerritoryStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.paint import read_paint
from vcmi_mapgen.core.reading.palette import palette_regions, same_share
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.border_kinds import draw_kinds
from vcmi_mapgen.core.steps.terrain_gen.coastline import Shore, SurfaceForm, target_gap
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import (
    Gate,
    GateGround,
    carve_gate_sites,
    gate_anchor_points,
    plan_gates,
)
from vcmi_mapgen.core.steps.terrain_gen.homes import choose_homes, room_side, room_tiles
from vcmi_mapgen.core.steps.terrain_gen.identity import (
    Palette,
    assign_dominants,
    town_terrains,
)
from vcmi_mapgen.core.steps.terrain_gen.layout import home_gap
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.paint import paint_places, paint_priors
from vcmi_mapgen.core.steps.terrain_gen.palette import draw_palette
from vcmi_mapgen.core.steps.terrain_gen.place_map import (
    flood_places,
    front_cells,
    label_adjacency,
    label_borders,
    reconcile_places,
)
from vcmi_mapgen.core.steps.terrain_gen.result import (
    LevelPlaces,
    PlaceMap,
    PlannedDoor,
    PlannedPlace,
)
from vcmi_mapgen.core.steps.terrain_gen.roles import label_roles
from vcmi_mapgen.core.steps.terrain_gen.shapes import grow_shapes, shape_caps
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import (
    Across,
    draw_doors,
    draw_partition,
    draw_territory_record,
    home_budget,
    islanded,
    merge_dull,
    settle,
    stranded,
    territory_plan,
    unreached,
    wall_depths,
    wall_kinds,
)

UNDERGROUND_SALT = 0x51E9
UNDERGROUND_ENTRANCE_W = 1
type Pair = tuple[int, int]

BARRIERS = frozenset((Terrain.WATER.value, Terrain.ROCK.value))
MAX_BRIDGE_ROUNDS = 8


@dataclass(frozen=True, slots=True)
class Front:
    """How ``bordered`` draws one level's front: the level, which keys its streams, the
    width of each gated passage, the hop links across to the other level, and the territory
    of each place when the caller drew them already, with the tiles under which a neutral
    territory is dull."""

    level: int = 0
    gated_w: int = ENTRANCE_W
    across: Across = field(default_factory=Across)
    drawn: tuple[int, ...] | None = None
    floor: float | None = None


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
    """The painted surface, its place map with its bands, and lines on how the shapes, the
    water and the palette went. The shapes grow on the form's land, the homes and the
    territories stand on them, a neutral territory too small to expect a prize joins its
    neighbour, the form floods its water, and the roles label the shapes
    before the palette paints them."""
    macro = priors.terrain[0].macro
    stats = priors.places[0]
    spread = priors.territories.get(0, TerritoryStats())
    coastline = form.land(priors, seed, options)
    land = coastline.land
    caps = shape_caps(
        stats, options.players, (coastline.planned, land_count_of(land)), stream(seed, "places")
    )
    layout = grow_shapes(land, caps, stream(seed, "layout"))
    record = territory_record(spread, options.players, coastline.planned, seed)
    budget = home_budget(record, land_count(layout.label))
    homes = choose_homes(
        layout, options.players, (target_gap(stats), budget), stream(seed, "homes")
    )
    owners: list[int | None] = [None] * layout.places
    for player, home in enumerate(homes.places):
        owners[home] = player
    grown = label_adjacency(layout.label)
    drawn = draw_territories(owners, (layout.label, grown), record, seed)
    territory, _ = settle(drawn, owners, grown)
    doors = draw_doors(territory, grown, spread.pair_doors, stream(seed, "water_doors"))
    keep = frozenset(t for point in homes.points for t in room_tiles(point, room_side()))
    shore = Shore(
        layout,
        territory,
        frozenset(doors),
        wall_depths(territory, doors, options.size),
        keep,
    )
    layout, water_log = form.flood(shore, priors, seed, options)
    adjacency = label_adjacency(layout.label)
    territory, _ = settle(territory, owners, adjacency)
    roles = label_roles(layout, homes.places, territory, stats, stream(seed, "roles"))
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
    after = home_gap([[z >= 0 for z in row] for row in layout.label], homes.points)
    line = (
        f"  places: {len(caps)} drawn, {layout.places} grown, "
        + f"home gap {homes.gap:.2f} ({after:.2f} after water)"
    )
    places = {i: PlannedPlace(roles[i], owners[i], dominants[i]) for i in range(layout.places)}
    plan = reconcile_places(grid, LevelPlaces(layout.label, places, adjacency))
    plan = bordered(
        plan,
        (stats, spread),
        options.players,
        seed,
        Front(drawn=carried(plan.label, layout.label, territory), floor=record.prize_tiles),
    )
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
        *water_log,
        palette_line(k, painted.grid, plan),
        border_line(plan),
        territory_line(plan),
    )
    return painted.grid, plan, lines


def land_count_of(land: Sequence[Sequence[bool]]) -> int:
    """The land tiles of a land mask."""
    return sum(1 for row in land for v in row if v)


def carried(
    label: Sequence[Sequence[int]], before: Sequence[Sequence[int]], territory: Sequence[int]
) -> tuple[int, ...]:
    """The territory of each place of ``label``: the one most of its tiles held in
    ``before``, else the one most of its neighbours hold, else a territory of its own. A
    place cut off from the rest of the territory its tiles held, and not the place holding
    most of that territory's tiles, takes the one most of its neighbours hold instead."""
    votes = _votes(label, before, territory)
    n = 1 + max((z for row in label for z in row), default=-1)
    out: dict[int, int] = {
        z: min(votes[z], key=lambda t: (-votes[z][t], t)) for z in range(n) if votes[z]
    }
    nbr: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in label_adjacency(label):
        nbr[a].add(b)
        nbr[b].add(a)
    core = {t: max(out, key=lambda z: (votes[z][t], -z)) for t in set(out.values())}
    for z in sorted(out):
        t = out[z]
        if core[t] != z and not any(out.get(q) == t for q in nbr[z]):
            out[z] = _most_held(out, nbr[z], t)
    fresh = max(territory, default=-1) + 1
    for z in range(n):
        if z not in out:
            out[z] = _most_held(out, nbr[z], fresh)
            if out[z] == fresh:
                fresh += 1
    return tuple(out[z] for z in range(n))


def _votes(
    label: Sequence[Sequence[int]], before: Sequence[Sequence[int]], territory: Sequence[int]
) -> dict[int, collections.Counter[int]]:
    """For each place of ``label``, how many of its tiles each territory held in
    ``before``."""
    votes: dict[int, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    for row, old in zip(label, before, strict=True):
        for z, o in zip(row, old, strict=True):
            if z >= 0 and o >= 0:
                votes[z][territory[o]] += 1
    return votes


def _most_held(out: Mapping[int, int], near: Iterable[int], default: int) -> int:
    """The territory most of the places ``near`` hold in ``out``, ``default`` when none
    holds one."""
    held = collections.Counter(out[q] for q in near if q in out)
    return min(held, key=lambda t: (-held[t], t)) if held else default


def territory_record(
    spread: TerritoryStats, players: int, land: int, seed: int, level: int = 0
) -> TerritoryCount:
    """The corpus record one level draws its territory count and home budget from: one
    map near ``players`` and ``land`` tiles."""
    return draw_territory_record(
        spread.counts_by_map, players, land, _stream(seed, "territory_count", level)
    )


def place_sizes(label: Sequence[Sequence[int]], places: int) -> list[int]:
    """The tiles of each of ``places`` places in ``label``."""
    sizes = [0] * places
    for row in label:
        for z in row:
            if 0 <= z < places:
                sizes[z] += 1
    return sizes


def draw_territories(
    owners: Sequence[int | None],
    places: tuple[Sequence[Sequence[int]], Collection[Pair]],
    record: TerritoryCount,
    seed: int,
    level: int = 0,
) -> tuple[int, ...]:
    """The territory of each place of ``places``, a label grid and its adjacency, split to
    the territory count and the home budget of ``record``. A neutral territory under the
    record's ``prize_tiles`` expects no prize, so it joins the neighbour it shares the
    longest border with. The ids of the territories that merged away stay empty."""
    label, adjacency = places
    sizes = place_sizes(label, len(owners))
    drawn = draw_partition(owners, adjacency, sizes, record, _stream(seed, "territories", level))
    return merge_dull(drawn, owners, label_borders(label), sizes, record.prize_tiles)


def land_count(label: Sequence[Sequence[int]]) -> int:
    """The tiles of ``label`` that belong to a place."""
    return sum(1 for row in label for z in row if z >= 0)


def _stream(seed: int, name: str, level: int) -> random.Random:
    return stream(seed, name, level) if level else stream(seed, name)


def bordered(
    plan: LevelPlaces,
    priors: tuple[PlaceStats, TerritoryStats],
    players: int,
    seed: int,
    front: Front | None = None,
) -> LevelPlaces:
    """``plan`` split into territories, as many as one corpus map near ``players`` and its
    land holds unless ``front`` brings them drawn, with the kind of every inner pair drawn
    from the corpus table, a door on each border the territories need, every other
    territory border walled, and the passages across them. ``front`` gives the level, the
    width of its gated passages, the hop links across to the other level, the drawn
    territories and the floor under which a neutral territory is dull. A neutral territory
    the grown places left under that floor joins its longest-bordering neighbour."""
    stats, spread = priors
    front = front or Front()
    level = front.level
    roles = {p: place.role for p, place in plan.places.items()}
    owners = [plan.places[p].owner for p in sorted(plan.places)]
    realised = label_adjacency(plan.label)
    drawn, floor = front.drawn, front.floor
    if drawn is None:
        record = territory_record(spread, players, land_count(plan.label), seed, level)
        drawn = draw_territories(owners, (plan.label, realised), record, seed, level)
        floor = record.prize_tiles
    sizes = place_sizes(plan.label, len(owners))
    drawn = merge_dull(drawn, owners, label_borders(plan.label), sizes, floor)
    territory, lords = settle(drawn, owners, realised)
    inner = [e for e in sorted(realised) if territory[e[0]] == territory[e[1]]]
    drawn_kinds = draw_kinds(roles, inner, stats.adjacency, _stream(seed, "borders", level))
    links = front.across.links(territory)
    doors = draw_doors(territory, realised, spread.pair_doors, _stream(seed, "doors", level), links)
    kinds = wall_kinds(territory, realised, drawn_kinds, doors)
    passages = plan_passages(plan.label, kinds, doors, front.gated_w)
    return replace(
        plan,
        kinds=kinds,
        passages=passages,
        territories=territory_plan(territory, lords, doors, passages),
        depths=wall_depths(territory, doors, len(plan.label), links),
    )


def relinked(plan: LevelPlaces, across: Across) -> LevelPlaces:
    """``plan`` with its wall widths from the hops over its doors and ``across``."""
    tp = plan.territories
    territory = [tp.zones[z] for z in sorted(tp.zones)]
    doors = {d.zones for d in tp.doors}
    return replace(
        plan, depths=wall_depths(territory, doors, len(plan.label), across.links(territory))
    )


def underground_places(
    plan: LevelPlaces,
    priors: tuple[PlaceStats, TerritoryStats],
    seed: int,
    links: Across | None = None,
) -> LevelPlaces:
    """The underground's places ``plan``, one per same-terrain region as ``flood_places``
    gives them, split by ``bordered`` with no home into as many territories as one corpus
    underground and its land holds. Each gated passage is ``UNDERGROUND_ENTRANCE_W`` wide,
    and ``links`` joins the territories through the gates to the surface."""
    front = Front(1, UNDERGROUND_ENTRANCE_W, links or Across())
    return bordered(plan, priors, 0, seed, front)


def gate_doors(
    gates: Sequence[Gate], plans: tuple[LevelPlaces, LevelPlaces]
) -> tuple[PlannedDoor, ...]:
    """Each planned gate as a door: its zone, territory and owner on the surface, then
    underground, and its tile on both."""
    sides = [p.territories for p in plans]
    out: list[PlannedDoor] = []
    for tile, zones in gates:
        ts = tuple(tp.zones[z] for tp, z in zip(sides, zones, strict=True))
        owners = tuple(tp.owners[t] for tp, t in zip(sides, ts, strict=True))
        out.append(PlannedDoor(zones, (ts[0], ts[1]), (owners[0], owners[1]), (tile, tile)))
    return tuple(out)


def gate_links(gates: Sequence[Gate], level: int, other: LevelPlaces) -> Across:
    """The hop links from ``level`` to the ``other`` level: each gate from its zone here to
    its territory there, and the territory pairs the other level's doors join."""
    tp = other.territories
    return Across(
        tuple((zones[level], tp.zones[zones[1 - level]]) for _, zones in gates),
        frozenset(d.territories for d in tp.doors),
    )


def territory_line(plan: LevelPlaces, name: str = "territories") -> str:
    """How many territories each kind of owner holds, their doors, the homes no door opens
    on a land border, the homes water parts from every other territory, and the
    territories on a home's land no home reaches over the doors."""
    tp = plan.territories
    players = sum(o is not None for o in tp.owners)
    walls = sum(
        1
        for (a, b), kind in plan.kinds.items()
        if kind == AdjacencyKind.CLOSED and tp.zones[a] != tp.zones[b]
    )
    realised = label_adjacency(plan.label)
    lost, islands = stranded(tp, realised), islanded(tp, realised)
    cut = unreached(tp, realised)
    return (
        f"  {name}: {len(tp.owners)}, {players} player, {len(tp.owners) - players} "
        + f"neutral, {len(tp.doors)} doors, {walls} walled borders"
        + (f", stranded players {lost}" if lost else "")
        + (f", players alone on their land {islands}" if islands else "")
        + (f", territories no home reaches {cut}" if cut else "")
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
    priors: TerrainPriors,
    surface_grid: Sequence[Sequence[Terrain]],
    anchors: list[Tile],
    seed: int,
    size: int,
) -> tuple[list[list[int]], frozenset[Tile]]:
    """Today's underground with its gate sites carved around ``anchors``, and its tunnel
    cells. The surface copy the carving paints is thrown away."""
    protect: set[Tile] = set()
    grid1 = MTOPO.generate(
        size, seed ^ UNDERGROUND_SALT, priors, MTOPO.MacroOptions(level=1), protect_out=protect
    )
    scratch = [[t.value for t in row] for row in surface_grid]
    protect |= carve_gate_sites(scratch, grid1, anchors, seed)
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
        size = options.size
        anchors = gate_anchor_points(size, size, seed)
        raw1, tunnels = underground(priors.terrain[1], grid0, anchors, seed, size)
        grid1 = despeckle(raw1, catalog.thin_terrains(), tunnels)
        flood = flood_places(grid1, UNDERGROUND_ENTRANCE_W)
        rng = stream(seed, "gates")
        spacing = (priors.gates.draw_count(size, rng), priors.gates.min_gap(size))
        fronts = front_cells(plan0.label) | front_cells(flood.label)
        room = room_offsets(catalog.subterranean_gate().footprint)
        ground = GateGround((plan0.label, flood.label), fronts, room)
        gates = plan_gates(anchors, ground, spacing, rng)
        plan1 = underground_places(
            flood,
            (priors.places[1], priors.territories.get(1, TerritoryStats())),
            seed,
            gate_links(gates, 1, plan0),
        )
        plan0 = relinked(plan0, gate_links(gates, 0, plan1))
        protect = tunnels - front_cells(plan1.label)
        lines = (
            *lines,
            territory_line(plan1, "underground territories"),
            f"  gates: {len(gates)} planned of {spacing[0]} drawn",
        )
        places = PlaceMap({0: plan0, 1: plan1}, gate_doors(gates, (plan0, plan1)))
        return TerrainDraw({0: grid0, 1: grid1}, protect, places, lines)
