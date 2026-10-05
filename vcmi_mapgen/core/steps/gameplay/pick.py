"""Which object of a family stands on a site's terrain: the corpus sprite weights draw it,
and a sprite the map already shows weighs less."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.identity import pick_kind
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import family_level, family_purpose
from vcmi_mapgen.core.steps.gameplay.economy import mine_variants
from vcmi_mapgen.core.steps.gameplay.landmark import above_top_tier

RANDOM_SHARE = 0.7
RANDOM_DWELLING_SHARE = 0.8
USED_WEIGHT = 0.05


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
    """Draws one object of a family for a terrain, from one map-wide stream."""

    catalog: Catalog
    rng: random.Random
    has_water: bool = False
    has_subterrain: bool = False
    used: set[str] = field(default_factory=set[str])

    def use(self, ident: Identity) -> None:
        """Mark ``ident``'s sprite as shown."""
        self.used.add(ident.kind.lower())

    def pick(self, family: str, terrain: str, st: TerrainStats) -> Pick | None:
        """One object of ``family`` for ``terrain``, None when the terrain offers none."""
        purpose = family_purpose(family)
        if purpose == Purpose.TOWN:
            pool = self.catalog.candidates(Purpose.TOWN, terrain)
            if self.rng.random() < RANDOM_SHARE:
                return Pick(self.catalog.random_town(), pool)
            return self._weighted(pool, purpose, st)
        if purpose == Purpose.MINE:
            res = family.partition(":")[2]
            ids = self.catalog.mines_by_resource(terrain).get(res, [])
            return self._weighted(mine_variants(ids, st.anim_w.get(purpose, {})), purpose, st)
        if purpose == Purpose.DWELLING:
            return self._dwelling(family_level(family) or 0, terrain, st)
        if purpose == Purpose.INFO:
            pool = info_pool(self.catalog, terrain, self.has_water, self.has_subterrain)
            return self._weighted(pool, purpose, st)
        return self._weighted(self.catalog.candidates(purpose, terrain), purpose, st)

    def _dwelling(self, level: int, terrain: str, st: TerrainStats) -> Pick | None:
        rand = self.catalog.random_dwelling(level or None)
        if level == 0:
            return Pick(rand, [rand])
        fixed = [
            i
            for i in self.catalog.candidates(Purpose.DWELLING, terrain)
            if not above_top_tier(self.catalog, i)
            and (self.catalog.dwelling_level(i.kind) or 0) == level
        ]
        if fixed and self.rng.random() >= RANDOM_DWELLING_SHARE:
            picked = self._weighted(fixed, Purpose.DWELLING, st)
            if picked is not None:
                return picked
        return Pick(rand, [rand, *fixed])

    def _weighted(self, pool: Iterable[Identity], purpose: str, st: TerrainStats) -> Pick | None:
        ids = list(pool)
        w = st.anim_w.get(purpose, {})
        ident = pick_kind(
            ids,
            lambda i: cast(
                float,
                (w.get(i.kind.lower(), 0) ** 0.5 + 0.3)
                * (USED_WEIGHT if i.kind.lower() in self.used else 1.0),
            ),
            self.rng,
        )
        return None if ident is None else Pick(ident, ids)
