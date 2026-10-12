"""Which object of a family stands on a site's terrain: the corpus sprite weights draw it, a
sprite the map already shows weighs less, and so does a kind with copies standing near the
spot. A town's creatures come only from a random dwelling, which takes the faction of the
town nearest in hero-days, so only a dwelling of neutral creatures stands fixed."""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import cast

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.identity import pick_kind
from vcmi_mapgen.core.planning.landmarks import above_top_tier
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import family_level, family_purpose
from vcmi_mapgen.core.reading.repeats import NEAR, Kind, Spot, kind_of
from vcmi_mapgen.core.reading.supply import apart
from vcmi_mapgen.core.steps.gameplay.economy import mine_variants

RANDOM_SHARE = 0.7
RANDOM_DWELLING_SHARE = 0.8
USED_WEIGHT = 0.05
NEAR_WEIGHT = 0.1


def info_pool(
    catalog: Catalog, terrain: str, has_water: bool, has_subterrain: bool = False
) -> list[Identity]:
    """`catalog.candidates(Purpose.INFO, terrain)`, minus cartographer subtypes the map
    can't back up:
    cartographerSubterranean is dropped unless the map actually has a second level, and
    cartographerWater is dropped on maps with no water at all."""
    pool = catalog.candidates(Purpose.INFO, terrain)
    return [
        i
        for i in pool
        if (i.subtype != "cartographerSubterranean" or has_subterrain)
        and (i.subtype != "cartographerWater" or has_water)
    ]


@dataclass(frozen=True, slots=True)
class Pick:
    """The object drawn, and the pool a smaller one may come from."""

    ident: Identity
    pool: list[Identity]


@dataclass(slots=True)
class Picker:
    """Draws one object of a family for a terrain, from one map-wide stream. Each copy of a
    kind standing within NEAR tiles of the spot on its level weighs the kind down by
    NEAR_WEIGHT."""

    catalog: Catalog
    rng: random.Random
    has_water: bool = False
    has_subterrain: bool = False
    used: set[str] = field(default_factory=set[str])
    stood: dict[Kind, list[Spot]] = field(default_factory=dict[Kind, list[Spot]])

    def use(self, ident: Identity, obj: PlacedObject | None = None) -> None:
        """Mark ``ident``'s sprite as shown and, when ``obj`` is given, its kind as standing
        where ``obj`` stands."""
        self.used.add(ident.kind.lower())
        if obj is not None:
            self.stood.setdefault(kind_of(ident), []).append((obj.level, obj.x, obj.y))

    def see(self, objs: Iterable[PlacedObject]) -> None:
        """Count the kinds of ``objs``, already standing, as standing where they stand."""
        for o in objs:
            ident = self.catalog.identity_of(o.kind)
            self.stood.setdefault(kind_of(ident), []).append((o.level, o.x, o.y))

    def near(self, ident: Identity, at: Spot | None) -> int:
        """The copies of ``ident``'s kind standing within NEAR tiles of ``at`` on its level."""
        if at is None:
            return 0
        level, x, y = at
        spots = self.stood.get(kind_of(ident), ())
        return sum(lv == level and apart((x, y), (sx, sy)) <= NEAR for lv, sx, sy in spots)

    def clear_first(self, ident: Identity, level: int, centres: Sequence[Tile]) -> list[Tile]:
        """``centres`` on ``level`` with the ones no copy of ``ident``'s kind stands near
        first, each side in its order."""
        return sorted(centres, key=lambda c: self.near(ident, (level, *c)) > 0)

    def pick(
        self, family: str, terrain: str, st: TerrainStats, at: Spot | None = None
    ) -> Pick | None:
        """One object of ``family`` for ``terrain`` at the spot ``at``, None when the terrain
        offers none."""
        purpose = family_purpose(family)
        if purpose == Purpose.TOWN:
            pool = self.catalog.candidates(Purpose.TOWN, terrain)
            if self.rng.random() < RANDOM_SHARE:
                return Pick(self.catalog.random_town(), pool)
            return self._weighted(pool, purpose, st, at)
        if purpose == Purpose.MINE:
            res = family.partition(":")[2]
            ids = self.catalog.mines_by_resource(terrain).get(res, [])
            variants = mine_variants(ids, st.anim_w.get(purpose, {}))
            return self._weighted(variants, purpose, st, at)
        if purpose == Purpose.DWELLING:
            return self._dwelling(family_level(family) or 0, terrain, st, at)
        if purpose == Purpose.INFO:
            pool = info_pool(self.catalog, terrain, self.has_water, self.has_subterrain)
            return self._weighted(pool, purpose, st, at)
        return self._weighted(self.catalog.candidates(purpose, terrain), purpose, st, at)

    def _dwelling(self, level: int, terrain: str, st: TerrainStats, at: Spot | None) -> Pick | None:
        rand = self.catalog.random_dwelling(level or None)
        if level == 0:
            return Pick(rand, [rand])
        fixed = [
            i
            for i in self.catalog.candidates(Purpose.DWELLING, terrain)
            if not above_top_tier(self.catalog, i)
            and self.catalog.dwelling_faction(i.kind) is None
            and (self.catalog.dwelling_level(i.kind) or 0) == level
        ]
        if fixed and self.rng.random() >= RANDOM_DWELLING_SHARE:
            picked = self._weighted(fixed, Purpose.DWELLING, st, at)
            if picked is not None:
                return picked
        return Pick(rand, [rand, *fixed])

    def _weighted(
        self, pool: Iterable[Identity], purpose: str, st: TerrainStats, at: Spot | None
    ) -> Pick | None:
        ids = list(pool)
        w = st.anim_w.get(purpose, {})
        ident = pick_kind(
            ids,
            lambda i: cast(
                float,
                (w.get(i.kind.lower(), 0) ** 0.5 + 0.3)
                * (USED_WEIGHT if i.kind.lower() in self.used else 1.0)
                * NEAR_WEIGHT ** self.near(i, at),
            ),
            self.rng,
        )
        return None if ident is None else Pick(ident, ids)
