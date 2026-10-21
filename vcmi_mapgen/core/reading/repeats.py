"""How often a visitable stands beside a copy of its kind. A kind is the object's type and
subtype, so sprite variants of one object count as copies. The share counts the visitables
whose kind stands more than once on their level, and of those the ones with a copy within a
given number of tiles. The spacing of copies is read apart, as the normalised distance u of a
copy to its nearest one on the level."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.supply import apart

NEAR = 10
SIDE = 6
REPEATED = frozenset({*VISIT_PURPOSES, Purpose.BANK})
SPACED = frozenset({*REPEATED, Purpose.MINE, Purpose.DWELLING})

type Kind = tuple[str | None, str | None]
type Spot = tuple[int, int, int]


def kind_of(ident: Identity) -> Kind:
    """The kind a copy shares: the identity's type and subtype."""
    return (ident.type, ident.subtype)


def visitables(catalog: Catalog, objs: Iterable[PlacedObject]) -> list[tuple[Kind, Spot]]:
    """The visitables of ``objs``, each with its kind and its level and tile."""
    return [
        (kind_of(catalog.identity_of(o.kind)), (o.level, o.x, o.y))
        for o in objs
        if purpose_of(catalog, o) in REPEATED
    ]


def nearest_copies(catalog: Catalog, objs: Iterable[PlacedObject]) -> list[int]:
    """Per visitable whose kind stands more than once on its level, the tiles to its nearest
    copy there."""
    found = visitables(catalog, objs)
    out: list[int] = []
    for i, (kind, (level, x, y)) in enumerate(found):
        gaps = [
            apart((x, y), (bx, by))
            for j, (k, (lv, bx, by)) in enumerate(found)
            if j != i and k == kind and lv == level
        ]
        if gaps:
            out.append(min(gaps))
    return out


def repeat_share(gaps: Iterable[int], within: int) -> float:
    """The share of ``gaps`` within ``within`` tiles, zero when there is none."""
    seen = list(gaps)
    return sum(g <= within for g in seen) / len(seen) if seen else 0.0


def copy_u(x: float, n: float, land: int) -> float:
    """The normalised nearest-copy distance u = n * pi * x^2 / land of a copy ``x`` tiles from
    its nearest of ``n`` on ``land`` land tiles. Random placement gives u an exponential law
    of scale 1."""
    return n * math.pi * x * x / land


def kind_key(kind: Kind) -> str:
    """The key a kind has in the spacing prior: its type and subtype joined by a colon, an
    absent part written empty."""
    return f"{kind[0] or ''}:{kind[1] or ''}"


def level_land(state: MapState) -> dict[int, int]:
    """The land tiles of each level of ``state``."""
    return {
        level: sum(t.is_land for row in grid for t in row) for level, grid in state.terrain.items()
    }


def copy_spacing(catalog: Catalog, state: MapState) -> list[tuple[Kind, str, float]]:
    """Per spaced object whose kind stands at least twice on its level, its kind, its purpose
    and the u of its Euclidean distance to the nearest other copy there, in level and object
    order."""
    groups: defaultdict[tuple[Kind, int], list[tuple[int, PlacedObject, str]]] = defaultdict(list)
    for index, o in enumerate(state.objs):
        purpose = purpose_of(catalog, o)
        if purpose in SPACED:
            groups[(kind_of(catalog.identity_of(o.kind)), o.level)].append((index, o, purpose))
    land = level_land(state)
    out: list[tuple[int, int, Kind, str, float]] = []
    for (kind, level), members in groups.items():
        n = len(members)
        if n < 2 or not land.get(level):
            continue
        for i, (index, o, purpose) in enumerate(members):
            gap = min(
                math.hypot(o.x - b.x, o.y - b.y) for j, (_k, b, _p) in enumerate(members) if j != i
            )
            out.append((level, index, kind, purpose, copy_u(gap, n, land[level])))
    out.sort(key=lambda r: (r[0], r[1]))
    return [(kind, purpose, u) for _lv, _i, kind, purpose, u in out]
