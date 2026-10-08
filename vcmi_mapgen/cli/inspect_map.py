"""Print what the shared readers see on one map: one tile, the objects near a tile, or the
cheapest hero route between two tiles or two players. The map is a `.vmap` from any folder,
a corpus map by name, or a seed generated in memory, and all three go through the same
readers."""

from __future__ import annotations

import argparse
import contextlib
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Role, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.effort import Effort, effort_map
from vcmi_mapgen.core.reading.ground import TownKey, purpose_of
from vcmi_mapgen.core.reading.places import infer_places, owners_of
from vcmi_mapgen.core.reading.routes import RouteMap, Spot, route_map
from vcmi_mapgen.corpus.maps import all_map_names, load_corpus_map
from vcmi_mapgen.corpus.mine.places import map_players
from vcmi_mapgen.vcmi.load import load_map, map_owners

type End = Tile | int

_MASK = {
    Role.BLOCKING: "B",
    Role.ENTRANCE: "E",
    Role.VISIT: "V",
    Role.OVERLAY: "o",
    Role.APPROACH: "a",
}


@dataclass(frozen=True, slots=True)
class Loaded:
    """One map open for inspection: its name, its state and the owner of each owned town."""

    name: str
    state: MapState
    owners: Mapping[TownKey, int]


@dataclass(frozen=True, slots=True)
class Guard:
    """A monster, its creature level and the tiles its zone of control covers."""

    obj: PlacedObject
    level: int
    zone: frozenset[Spot]


@dataclass(frozen=True, slots=True)
class Trip:
    """The cheapest hero route between two ends: its effort, its tiles from the start and the
    guards whose zone it enters, in the order the hero meets them."""

    effort: Effort
    tiles: tuple[Spot, ...]
    paid: tuple[Guard, ...]


@dataclass(frozen=True, slots=True)
class RouteAsk:
    """The two ends of a route, the level a tile end stands on, and whether to list the
    route's tiles."""

    ends: tuple[End, End]
    level: int = 0
    verbose: bool = False


def from_vmap(path: Path) -> Loaded:
    """A `.vmap` from any folder, with the owners its towns carry."""
    return Loaded(path.stem, load_map(str(path)), map_owners(str(path)))


def from_corpus(settings: Settings, name: str) -> Loaded:
    """The corpus map ``name``, with the owners its `.h3m` names."""
    if name not in all_map_names(settings.maps_dir):
        raise SystemExit(f"no corpus map named {name!r} in {settings.maps_dir}")
    owners = map_players(settings.h3m_dir, name).owners
    return Loaded(name, load_corpus_map(settings.maps_dir, name), owners)


def from_seed(catalog: Catalog, priors: Priors, config: StepConfig) -> Loaded:
    """The map the whole pipeline generates for ``config``, kept in memory."""
    pipeline = Pipeline(catalog, config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    with contextlib.redirect_stdout(io.StringIO()):
        state = pipeline.run()
    return Loaded(f"seed {config.seed} size {config.size}", state, owners_of(state))


def parse_tile(text: str) -> Tile:
    """``x,y`` as a tile."""
    try:
        x, y = (int(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"a tile is x,y, not {text!r}") from None
    return x, y


def parse_end(text: str) -> End:
    """``P<n>`` as player n, or ``x,y`` as a tile."""
    if text[:1] in ("P", "p") and text[1:].isdigit():
        return int(text[1:])
    return parse_tile(text)


def guards(catalog: Catalog, state: MapState) -> list[Guard]:
    """Every monster with a creature level, and its zone: the tiles around its visit tile
    that share its ground, land or water."""
    out: list[Guard] = []
    for o in state.objs:
        level = catalog.creature_level(o.kind)
        grid = state.terrain.get(o.level)
        if level is None or grid is None:
            continue
        zone = {
            n
            for s in _visits(o)
            if _inside(state, s.x, s.y)
            for n in _ring(s)
            if _inside(state, n.x, n.y) and grid[n.y][n.x].is_water == grid[s.y][s.x].is_water
        }
        out.append(Guard(o, level, frozenset(zone)))
    return out


def tile_lines(catalog: Catalog, loaded: Loaded, at: Spot) -> list[str]:
    """The terrain of ``at``, the objects on it, whether a hero may stand on it, its place
    and the guards that watch it."""
    state = loaded.state
    grid = state.terrain.get(at.level)
    if grid is None or not _inside(state, at.x, at.y):
        return [f"no tile {at.x},{at.y} on level {at.level} of {loaded.name}"]
    road = state.roads.get(at.level, {}).get((at.x, at.y))
    lines = [
        f"tile {at.x},{at.y} level {at.level} of {loaded.name}: {_terrain(grid[at.y][at.x])}"
        + (f", {road.name.lower()} road" if road else ""),
        f"  hero: {'may stand here' if _open(route_map(catalog, state), at) else 'blocked'}",
    ]
    for o in state.objs:
        for (x, y), role in o.footprint.at(o.x, o.y):
            if o.level == at.level and (x, y) == (at.x, at.y):
                lines.append(f"  object {_describe(catalog, o)}, this tile {role}")
    lines.append(_place_line(catalog, loaded, at))
    watch = [g for g in guards(catalog, state) if at in g.zone]
    lines += [f"  guard {_describe(catalog, g.obj)} level {g.level}" for g in watch]
    if not watch:
        lines.append("  guard: none")
    return lines


def near_lines(catalog: Catalog, loaded: Loaded, at: Spot, radius: int) -> list[str]:
    """Every object with a cell within ``radius`` steps of ``at``, nearest first, with its
    mask and its visit tiles."""
    found: list[tuple[int, int, int, PlacedObject]] = []
    for o in loaded.state.objs:
        if o.level != at.level:
            continue
        far = min(max(abs(x - at.x), abs(y - at.y)) for (x, y), _role in o.footprint.at(o.x, o.y))
        if far <= radius:
            found.append((far, o.y, o.x, o))
    lines = [f"{len(found)} objects within {radius} of {at.x},{at.y} level {at.level}"]
    for far, _y, _x, o in sorted(found, key=lambda f: f[:3]):
        rows = ["".join(_MASK[r] if r else "." for r in row) for row in o.footprint.grid()]
        cells = [t for t, role in o.footprint.at(o.x, o.y) if role.interactive]
        visits = " ".join(f"{x},{y}" for x, y in cells) or "none"
        lines += [
            f"  {far}: {_describe(catalog, o)}",
            f"     mask {' / '.join(rows)}, visit {visits}",
        ]
    return lines


def ends_of(loaded: Loaded, end: End, level: int) -> list[Spot]:
    """The tiles one route end stands for: a tile, or the visit tiles of every town the
    player owns."""
    if isinstance(end, tuple):
        return [Spot(level, *end)]
    spots = [
        s
        for o in loaded.state.objs
        if loaded.owners.get((o.x, o.y, o.level)) == end
        for s in _visits(o)
    ]
    if not spots:
        raise SystemExit(f"P{end} owns no town on {loaded.name}")
    return spots


def trip(
    catalog: Catalog,
    state: MapState,
    start: Sequence[Spot],
    goal: Sequence[Spot],
    toll: Sequence[int],
) -> Trip | None:
    """The cheapest route from any of ``start`` to any of ``goal``. A goal a hero may stand
    on is reached. A goal an object blocks is visited from a tile beside it."""
    route = route_map(catalog, state)
    em = effort_map(route, start, toll)
    options: list[tuple[int, Effort, list[Spot]]] = []
    for g in goal:
        if _open(route, g):
            effort, tiles = em.at(g), em.path(g)
        else:
            effort, tiles = em.visit(g), [*em.way(g), g]
        if effort is not None:
            options.append((effort.total, effort, tiles))
    if not options:
        return None
    _total, effort, tiles = min(options, key=lambda o: o[0])
    met = [
        (min(i for i, t in enumerate(tiles) if t in g.zone), n, g)
        for n, g in enumerate(guards(catalog, state))
        if not g.zone.isdisjoint(tiles)
    ]
    return Trip(effort, tuple(tiles), tuple(g for _i, _n, g in sorted(met, key=lambda m: m[:2])))


def route_lines(catalog: Catalog, loaded: Loaded, ask: RouteAsk, toll: Sequence[int]) -> list[str]:
    """The cheapest route between two ends, its hero-days and every guard it pays."""
    a, b = (_label(e) for e in ask.ends)
    start, goal = (ends_of(loaded, e, ask.level) for e in ask.ends)
    found = trip(catalog, loaded.state, start, goal, toll)
    if found is None:
        return [f"no route from {a} to {b} on {loaded.name}"]
    e = found.effort
    lines = [
        f"route {a} -> {b} on {loaded.name}: {e.total} hero-days, {e.days} travel and "
        + f"{e.total - e.days} for the strongest guard, level {e.guard}, {len(found.tiles)} tiles"
    ]
    lines += [
        f"  guard {_describe(catalog, g.obj)} level {g.level} toll {toll[g.level]}"
        for g in found.paid
    ]
    if not found.paid:
        lines.append("  no guard on the way")
    if ask.verbose:
        lines.append("  tiles " + " ".join(f"{s.x},{s.y}" for s in found.tiles))
    return lines


def _inside(state: MapState, x: int, y: int) -> bool:
    return 0 <= x < state.size and 0 <= y < state.size


def _open(route: RouteMap, at: Spot) -> bool:
    grid = route.open.get(at.level)
    return grid is not None and grid[at.y][at.x]


def _ring(s: Spot) -> list[Spot]:
    return [Spot(s.level, s.x + dx, s.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def _visits(o: PlacedObject) -> list[Spot]:
    cells = [t for t, role in o.footprint.at(o.x, o.y) if role.interactive]
    return [Spot(o.level, x, y) for x, y in cells or [(o.x, o.y)]]


def _terrain(t: Terrain) -> str:
    return t.name.lower()


def _label(end: End) -> str:
    return f"P{end}" if isinstance(end, int) else f"{end[0]},{end[1]}"


def _describe(catalog: Catalog, o: PlacedObject) -> str:
    ident = catalog.identity_of(o.kind)
    name = "/".join(p for p in (ident.type, ident.subtype) if p) or o.kind
    return f"{name} ({o.kind}, {purpose_of(catalog, o)}) at {o.x},{o.y}"


def _place_line(catalog: Catalog, loaded: Loaded, at: Spot) -> str:
    inferred = infer_places(catalog, loaded.state, at.level, loaded.owners)
    label = inferred.labels[at.y][at.x] if inferred.labels else -1
    if label < 0:
        return "  place: none, water or rock"
    p = inferred.places[label]
    owner = "none" if p.owner is None else f"P{p.owner}"
    return (
        f"  place {label}: {p.role}, owner {owner}, {p.area} tiles, "
        + f"mostly {_terrain(p.dominant)}"
    )
