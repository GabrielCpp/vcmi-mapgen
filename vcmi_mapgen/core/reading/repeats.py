"""How often a visitable stands beside a copy of its kind. A kind is the object's type and
subtype, so sprite variants of one object count as copies. The share counts the visitables
whose kind stands more than once on their level, and of those the ones with a copy within a
given number of tiles."""

from __future__ import annotations

from collections.abc import Iterable

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.supply import apart

NEAR = 10
SIDE = 6
REPEATED = frozenset({*VISIT_PURPOSES, Purpose.BANK})

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
