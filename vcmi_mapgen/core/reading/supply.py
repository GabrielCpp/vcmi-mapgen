"""Each town's supply: the tiles from its entrance to the nearest sawmill and ore pit on its
level, and the towns with none within NEAR tiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.ground import purpose_of
from vcmi_mapgen.core.reading.promise import doors

SUPPLY = ("sawmill", "orePit")
NEAR = 12


def entrance(obj: PlacedObject) -> Tile:
    """The first entrance tile of ``obj``."""
    d = doors(obj)[0]
    return (d.x, d.y)


def apart(a: Tile, b: Tile) -> int:
    """The Chebyshev distance between two tiles."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass(frozen=True, slots=True)
class TownSupply:
    """One town and, per supply resource, the tiles to its nearest mine on the town's level,
    None when the level has none."""

    town: PlacedObject
    nearest: Mapping[str, int | None]

    def gaps(self) -> list[str]:
        """The supply resources with no mine within NEAR tiles."""
        return [r for r in SUPPLY if (d := self.nearest[r]) is None or d > NEAR]


def town_supply(catalog: Catalog, objs: Sequence[PlacedObject]) -> list[TownSupply]:
    """Every town of ``objs`` with its supply, in level, then tile order."""
    mines: dict[tuple[int, str], list[Tile]] = {}
    towns: list[PlacedObject] = []
    for o in objs:
        purpose = purpose_of(catalog, o)
        if purpose == Purpose.TOWN:
            towns.append(o)
        elif purpose == Purpose.MINE:
            res = catalog.identity_of(o.kind).subtype
            if res in SUPPLY:
                mines.setdefault((o.level, str(res)), []).append(entrance(o))
    out: list[TownSupply] = []
    for town in sorted(towns, key=lambda t: (t.level, t.x, t.y)):
        door = entrance(town)
        nearest = {
            r: min((apart(door, m) for m in mines.get((town.level, r), ())), default=None)
            for r in SUPPLY
        }
        out.append(TownSupply(town, nearest))
    return out


def supply_gaps(catalog: Catalog, objs: Sequence[PlacedObject]) -> list[str]:
    """One line per town missing a supply resource within NEAR tiles."""
    return [
        f"town at {s.town.x},{s.town.y} level {s.town.level}: no {r} within {NEAR} tiles"
        for s in town_supply(catalog, objs)
        for r in s.gaps()
    ]
