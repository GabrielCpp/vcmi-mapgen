"""Which family a gameplay object belongs to, and the hero-days a player needs to visit it.

A family is a mine resource, a dwelling level or one of the other gameplay purposes. The
effort runs from the nearest player town and leaves out the object's own guard, so it
measures where an object stands, not how hard it is guarded."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import FLANKED, Purpose
from vcmi_mapgen.core.reading.effort import effort_map
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.promise import doors
from vcmi_mapgen.core.reading.routes import Spot, route_map

FAR_DAYS = 40
TOP_LEVEL = 7

type Key = tuple[int, int, int]


def mine_family(resource: str) -> str:
    return f"{Purpose.MINE}:{resource}"


def dwelling_family(level: int) -> str:
    return f"{Purpose.DWELLING}:{level}"


def family_purpose(family: str) -> str:
    """The purpose a family belongs to."""
    return family.split(":", 1)[0]


def family_level(family: str) -> int | None:
    """The creature level of a dwelling family, 0 for any level, None for another family."""
    purpose, _, rest = family.partition(":")
    return int(rest) if purpose == Purpose.DWELLING and rest else None


@dataclass(frozen=True, slots=True)
class Families:
    """The family of each gameplay object. A random dwelling takes the level it stands for,
    0 for any level. A fixed dwelling takes the highest level it recruits, at most 7."""

    random_levels: Mapping[str, int]

    @staticmethod
    def of(catalog: Catalog) -> Families:
        levels = {catalog.random_dwelling(n).kind.lower(): n for n in range(1, TOP_LEVEL + 1)}
        levels[catalog.random_dwelling(None).kind.lower()] = 0
        return Families(levels)

    def family(self, catalog: Catalog, obj: PlacedObject) -> str | None:
        """The family of ``obj``, None when it is no gameplay object."""
        purpose = purpose_of(catalog, obj)
        if purpose not in FLANKED:
            return None
        if purpose == Purpose.MINE:
            subtype = catalog.identity_of(obj.kind).subtype
            return mine_family(str(subtype)) if subtype is not None else None
        if purpose == Purpose.DWELLING:
            kind = obj.kind.lower()
            if kind in self.random_levels:
                return dwelling_family(self.random_levels[kind])
            return dwelling_family(min(catalog.dwelling_level(obj.kind) or 0, TOP_LEVEL))
        return purpose


def unguarded(catalog: Catalog, state: MapState, objs: Iterable[PlacedObject]) -> MapState:
    """``state`` without the guards standing next to a door of ``objs``."""
    near = {
        (d.level, d.x + dx, d.y + dy)
        for o in objs
        for d in doors(o)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    }
    keep = [
        o
        for o in state.objs
        if not (purpose_of(catalog, o) == Purpose.GUARD and (o.level, o.x, o.y) in near)
    ]
    return replace(state, objs=keep)


def family_days(
    catalog: Catalog,
    state: MapState,
    homes: Sequence[Spot],
    skip: AbstractSet[Key],
    toll: Sequence[int],
) -> list[tuple[str, int]]:
    """Each gameplay object a home reaches with its family and its effort in days, its own
    guard left out. The objects at ``skip``, the player towns, stay out."""
    if not homes:
        return []
    families = Families.of(catalog)
    found = [
        (f, o)
        for o in state.objs
        if (o.x, o.y, o.level) not in skip and (f := families.family(catalog, o)) is not None
    ]
    view = unguarded(catalog, state, (o for _f, o in found))
    em = effort_map(route_map(catalog, view), homes, toll)
    out: list[tuple[str, int]] = []
    for f, o in found:
        efforts = [e.total for d in doors(o) if (e := em.visit(d)) is not None]
        if efforts:
            out.append((f, min(efforts)))
    return out


def histogram(days: Iterable[int]) -> tuple[int, ...]:
    """The count per day 0..FAR_DAYS, the last count holding every effort past it."""
    out = [0] * (FAR_DAYS + 1)
    for d in days:
        out[min(max(d, 0), FAR_DAYS)] += 1
    return tuple(out)
