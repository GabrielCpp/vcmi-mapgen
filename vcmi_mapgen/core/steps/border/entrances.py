"""Entrance guards: a hostile guard on most planned zone entrances."""

import random
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, Entrance, Guard, Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.guards import guard_spaced

ENTRANCE_GUARD_PROB = 0.85
ENTRANCE_SALT = 0xE47


@dataclass(frozen=True, slots=True)
class EntranceField:
    """One level's planned entrances per zone, each zone's tiles, the zones that host a
    player town, the zones no entrance guard may touch, and the tiles no guard may stand on."""

    plan: Mapping[int, Sequence[Entrance]]
    zone_tiles: Mapping[int, frozenset[Tile]]
    home_zids: Container[int]
    skip_zids: Container[int]
    avoid: Container[Tile]


def _guard_level(rng: random.Random, area: int, home: bool) -> int:
    if home:
        return 1
    return min(7, 1 + area // 200 + (1 if rng.random() < 0.4 else 0))


@final
class _EntranceGuards:
    def __init__(
        self, catalog: Catalog, field: EntranceField, objs: Sequence[PlacedObject], level: int
    ) -> None:
        self.catalog = catalog
        self.field = field
        self.level = level
        self.cover = CoverIndex(objs)
        self.blocked = FP.blocking_cells(objs)
        self.guards = [(o.x, o.y) for o in objs if o.purpose == Purpose.GUARD]
        self.out: list[PlacedObject] = []

    def _stands(self, guard: PlacedObject, ts: frozenset[Tile]) -> bool:
        cells = FP.interactive_cells(guard.footprint, guard.x, guard.y)
        return (
            all(c in ts and c not in self.blocked and c not in self.field.avoid for c in cells)
            and guard_spaced((guard.x, guard.y), self.guards)
            and self.cover.try_add(guard)
        )

    def _guard(self, gident: Identity, cands: Sequence[Tile], ts: frozenset[Tile]) -> None:
        for t in cands:
            guard = PlacedObject.at(
                gident, t, level=self.level, purpose=Purpose.GUARD, payload=Guard()
            )
            if self._stands(guard, ts):
                self.out.append(guard)
                self.guards.append(t)
                return

    def run(self, seed: int) -> list[PlacedObject]:
        field = self.field
        for zid in sorted(field.plan):
            if zid in field.skip_zids:
                continue
            ts = field.zone_tiles.get(zid, frozenset())
            rng = random.Random(seed ^ (zid * 7349) ^ (self.level * 7919) ^ ENTRANCE_SALT)
            for rep, band, other in sorted(field.plan[zid]):
                if zid >= other or other in field.skip_zids:
                    continue
                if rng.random() > ENTRANCE_GUARD_PROB:
                    continue
                gident = self.catalog.guard(_guard_level(rng, len(ts), zid in field.home_zids))
                self._guard(gident, [rep, *sorted(band)], ts)
        return self.out


def guard_entrances(
    catalog: Catalog, field: EntranceField, objs: Sequence[PlacedObject], seed: int, level: int
) -> list[PlacedObject]:
    """Guard each planned entrance with probability ``ENTRANCE_GUARD_PROB``.

    Only the lower zone id of a pair emits, so one crossing gets one guard. The guard stands
    on the entrance's representative tile, else on the first band tile that takes it: its
    interactive cell inside the zone, off every blocking cell and ``avoid`` tile, spaced
    from every other guard by ``guard_spaced``, and accepted by the cover index. A player
    zone's entrance guard is level 1. Any other zone's grows with its area. Entrances of a
    ``skip_zids`` zone stay unguarded here, because the gated step already controls them."""
    return _EntranceGuards(catalog, field, objs, level).run(seed)
