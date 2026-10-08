"""Print the territories of one level of an inspected map: each territory's owners, size,
zones, towns and doors, the links between territories, an ASCII map, and where the planned
territories part from the read ones."""

from __future__ import annotations

import string

from vcmi_mapgen.cli.inspect_map import Loaded
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.reading.places import infer_places
from vcmi_mapgen.core.reading.routes import RouteMap, route_map
from vcmi_mapgen.core.reading.territories import (
    NONE,
    Door,
    Territories,
    Territory,
    disagreements,
    islands,
    territories_from,
)

SYMBOLS = string.ascii_uppercase + string.ascii_lowercase + string.digits
LEGEND = "letters territories, ! door, + guarded or gated, . fragment, # blocked, ~ water"


def symbol(territory: int) -> str:
    """The letter a territory id prints as, ``*`` past the last letter."""
    return SYMBOLS[territory] if 0 <= territory < len(SYMBOLS) else "*"


def _count(n: int, one: str, many: str = "") -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


def _owner(t: Territory) -> str:
    return " ".join(f"P{p}" for p in t.owners) if t.owners else "neutral"


def _door(door: Door, of: int) -> str:
    others = ", ".join(symbol(i) for i in door.territories if i != of)
    level = "gate" if door.level is None and door.gated else f"level {door.level or '?'}"
    at = " ".join(f"{x},{y}" for x, y in sorted({b.anchor for b in door.barriers}))
    return f"     door to {others}: {level} at {at}"


def _rows(read: Territories, route: RouteMap) -> list[str]:
    doors = frozenset(t for d in read.doors for t in d.tiles)
    held = frozenset(t for b in read.barriers for t in b.tiles)
    walk, water = route.open[read.level], route.water[read.level]

    def cell(t: Tile) -> str:
        x, y = t
        if t in doors and t in held:
            return "!"
        if t in held:
            return "+"
        if read.at(t) != NONE:
            return symbol(read.at(t))
        if water[y][x]:
            return "~"
        return "." if walk[y][x] else "#"

    return ["".join(cell((x, y)) for x in range(route.size)) for y in range(route.size)]


def territory_lines(catalog: Catalog, loaded: Loaded, level: int) -> list[str]:
    """The territories of ``level``, its ASCII map, and its disagreements with the plan."""
    state = loaded.state
    route = route_map(catalog, state)
    read = territories_from(catalog, state, route, level, loaded.owners)
    if read is None:
        return [f"no level {level} on {loaded.name}"]
    places = infer_places(catalog, state, level, loaded.owners).places
    lines = [
        f"{_count(len(read.territories), 'territory', 'territories')}, "
        + f"{_count(len(read.doors), 'door')} and {_count(len(read.links), 'link')} "
        + f"on level {level} of {loaded.name}"
    ]
    alone = islands(read, route.water[level])
    for i, t in enumerate(read.territories):
        zones = ", ".join(f"{z} {places[z].role}" for z in t.zones) or "none"
        lines.append(
            f"  {symbol(i)} {_owner(t)}: {t.area} tiles, {_count(t.towns, 'town')}, zones {zones}"
        )
        lines += [_door(d, i) for d in read.doors if i in d.territories] or [
            "     no door: " + ("water parts it from the rest" if i in alone else "walled in")
        ]
    lines += [f"  link {symbol(a)}-{symbol(b)}" for a, b in read.links]
    lines += [f"map ({LEGEND}):", *_rows(read, route)]
    planned = loaded.planned.get(level)
    if planned is None:
        return [*lines, "planned: none published"]
    found = disagreements(planned, read)
    return [*lines, "planned: agrees" if not found else "planned:", *(f"  {d}" for d in found)]
