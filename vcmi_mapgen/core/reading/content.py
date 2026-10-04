"""The content of each place of one level: its rewards, their value and its guards, keyed
by the place's role and its hop count from the nearest home (map-math 3.4, Content)."""

import collections
from collections.abc import Iterable, Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.priors.places import PlaceContent
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.value import ValueTable, guard_level, value_of

UNREACHED = -1


def hops(pairs: Iterable[tuple[int, int]], sources: Iterable[int]) -> dict[int, int]:
    """The hop count from the nearest source to every place a source reaches over
    ``pairs``."""
    nbrs: dict[int, set[int]] = collections.defaultdict(set)
    for p, q in pairs:
        nbrs[p].add(q)
        nbrs[q].add(p)
    dist = dict.fromkeys(sources, 0)
    frontier = sorted(dist)
    while frontier:
        nxt: list[int] = []
        for p in frontier:
            for q in sorted(nbrs[p]):
                if q not in dist:
                    dist[q] = dist[p] + 1
                    nxt.append(q)
        frontier = nxt
    return dist


def _tile(obj: PlacedObject) -> Tile:
    cells = sorted(t for t, role in obj.footprint.at(obj.x, obj.y) if role.interactive)
    return cells[0] if cells else (obj.x, obj.y)


def _label(labels: Sequence[Sequence[int]], t: Tile) -> int:
    x, y = t
    if 0 <= y < len(labels) and 0 <= x < len(labels[y]):
        return labels[y][x]
    return -1


def place_content(
    catalog: Catalog,
    objs: Iterable[PlacedObject],
    labels: Sequence[Sequence[int]],
    roles: Mapping[int, str],
    hop: Mapping[int, int],
) -> tuple[PlaceContent, ...]:
    """One ``PlaceContent`` per place of ``roles``, in place id order. ``labels[y][x]`` is
    the place id of a tile, and an object counts in the place of its first interactive
    cell."""
    table = ValueTable.of(catalog)
    area = collections.Counter(p for row in labels for p in row if p in roles)
    rewards: collections.Counter[int] = collections.Counter()
    value: collections.Counter[int] = collections.Counter()
    guards: dict[int, list[int]] = collections.defaultdict(list)
    fixed: collections.Counter[int] = collections.Counter()
    for obj in objs:
        p = _label(labels, _tile(obj))
        if p not in roles:
            continue
        if purpose_of(catalog, obj) == Purpose.GUARD:
            level = guard_level(catalog, table, obj)
            if level is None:
                fixed[p] += 1
            else:
                guards[p].append(level)
            continue
        v = value_of(catalog, table, obj)
        if v > 0:
            rewards[p] += 1
            value[p] += v
    return tuple(
        PlaceContent(
            role=roles[p],
            hop=hop.get(p, UNREACHED),
            area=area[p],
            rewards=rewards[p],
            value=value[p],
            guards=tuple(sorted(guards[p])),
            fixed=fixed[p],
        )
        for p in sorted(roles)
    )
