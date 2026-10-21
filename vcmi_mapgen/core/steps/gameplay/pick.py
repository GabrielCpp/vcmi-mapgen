"""Which object of a family stands on a site's terrain: the corpus sprite weights draw it, and a
sprite the map already shows weighs less. The roster names the kind of a spaced slot first, and
the picker then draws only a sprite of that kind. A town's creatures come only from a random
dwelling, which takes the faction of the town nearest in hero-days, so only a dwelling of
neutral creatures stands fixed."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.identity import pick_kind
from vcmi_mapgen.core.planning.landmarks import above_top_tier
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.reading.families import family_level, family_purpose
from vcmi_mapgen.core.reading.repeats import Kind, Spot, kind_of
from vcmi_mapgen.core.steps.gameplay.economy import mine_variants

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
    """Draws one object of a family for a terrain, from one map-wide stream, and keeps where
    each kind stands."""

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

    def pick(
        self, family: str, terrain: str, st: TerrainStats, kind: Kind | None = None
    ) -> Pick | None:
        """One object of ``family`` for ``terrain``, of ``kind`` when given, None when the
        terrain offers none. A town ignores ``kind``."""
        purpose = family_purpose(family)
        if purpose == Purpose.TOWN:
            pool = self.catalog.candidates(Purpose.TOWN, terrain)
            if self.rng.random() < RANDOM_SHARE:
                return Pick(self.catalog.random_town(), pool)
            return self._weighted(pool, purpose, st)
        if purpose == Purpose.DWELLING:
            return self._dwelling(family_level(family) or 0, terrain, st, kind)
        return self._weighted(self._pool(family, terrain, st), purpose, st, kind)

    def kinds(self, family: str, terrain: str, st: TerrainStats) -> dict[Kind, float]:
        """The chance of each kind of ``family`` on ``terrain`` under the draw of `pick`, the
        used penalty left out, summing to 1. Empty when the terrain offers none, and for a
        town."""
        purpose = family_purpose(family)
        if purpose == Purpose.TOWN:
            return {}
        w = st.anim_w.get(purpose, {})
        if purpose == Purpose.DWELLING:
            return self._dwelling_kinds(family_level(family) or 0, terrain, w)
        return _normalised(self._by_kind(self._pool(family, terrain, st), w))

    def offers(self, family: str, terrain: str, st: TerrainStats, kind: Kind) -> bool:
        """Whether `pick` of ``family`` on ``terrain`` can return an object of ``kind``."""
        return kind in self.kinds(family, terrain, st)

    def _pool(self, family: str, terrain: str, st: TerrainStats) -> list[Identity]:
        purpose = family_purpose(family)
        if purpose == Purpose.MINE:
            res = family.partition(":")[2]
            ids = self.catalog.mines_by_resource(terrain).get(res, [])
            return mine_variants(ids, st.anim_w.get(purpose, {}))
        if purpose == Purpose.INFO:
            return info_pool(self.catalog, terrain, self.has_water, self.has_subterrain)
        return self.catalog.candidates(purpose, terrain)

    def _fixed(self, level: int, terrain: str) -> list[Identity]:
        return [
            i
            for i in self.catalog.candidates(Purpose.DWELLING, terrain)
            if not above_top_tier(self.catalog, i)
            and self.catalog.dwelling_faction(i.kind) is None
            and (self.catalog.dwelling_level(i.kind) or 0) == level
        ]

    def _dwelling(
        self, level: int, terrain: str, st: TerrainStats, kind: Kind | None
    ) -> Pick | None:
        rand = self.catalog.random_dwelling(level or None)
        if level == 0:
            return Pick(rand, [rand]) if kind in (None, kind_of(rand)) else None
        fixed = self._fixed(level, terrain)
        if kind is None:
            if fixed and self.rng.random() >= RANDOM_DWELLING_SHARE:
                picked = self._weighted(fixed, Purpose.DWELLING, st)
                if picked is not None:
                    return picked
            return Pick(rand, [rand, *fixed])
        if kind == kind_of(rand):
            return Pick(rand, [rand, *fixed])
        return self._weighted(fixed, Purpose.DWELLING, st, kind)

    def _dwelling_kinds(self, level: int, terrain: str, w: dict[str, int]) -> dict[Kind, float]:
        rand = kind_of(self.catalog.random_dwelling(level or None))
        fixed = _normalised(self._by_kind(self._fixed(level, terrain), w)) if level else {}
        if not fixed:
            return {rand: 1.0}
        out = {k: p * (1 - RANDOM_DWELLING_SHARE) for k, p in fixed.items()}
        out[rand] = out.get(rand, 0.0) + RANDOM_DWELLING_SHARE
        return out

    def _by_kind(self, pool: Iterable[Identity], w: dict[str, int]) -> dict[Kind, float]:
        out: dict[Kind, float] = {}
        for i in pool:
            if "random" not in (i.type or "").lower():
                out[kind_of(i)] = out.get(kind_of(i), 0.0) + _weight(i, w)
        return out

    def _weighted(
        self, pool: Iterable[Identity], purpose: str, st: TerrainStats, kind: Kind | None = None
    ) -> Pick | None:
        ids = list(pool)
        w = st.anim_w.get(purpose, {})
        ident = pick_kind(
            [i for i in ids if kind is None or kind_of(i) == kind],
            lambda i: _weight(i, w) * (USED_WEIGHT if i.kind.lower() in self.used else 1.0),
            self.rng,
        )
        return None if ident is None else Pick(ident, ids)


def _weight(ident: Identity, w: dict[str, int]) -> float:
    return cast(float, w.get(ident.kind.lower(), 0) ** 0.5 + 0.3)


def _normalised(weights: dict[Kind, float]) -> dict[Kind, float]:
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {}
