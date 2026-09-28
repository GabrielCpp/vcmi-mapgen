"""How many gameplay objects a zone holds, and which ones.

One total is drawn per zone at the corpus rate of counted objects per tile. The forced
objects (the player town with its economy pair, the zone's gates, a shipyard) count inside
that total, and the rest is split by the corpus mix of mines, dwellings, banks and
visitables. A neutral town takes three slots (itself and its economy pair) when the zone is
large enough and the total leaves room."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import cast, final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import COUNTED, VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.placement.identity import RND_DWELL, RND_DWELL_L, RND_TOWN, pick_kind
from vcmi_mapgen.core.placement.intensity import density, stoch_round
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.core.steps.gameplay.economy import ECONOMY, Ledger, mine_variants, rest_mines

DRAW_SALT = 0x5EED
TOWN_SLOTS = 3
MIX: tuple[str, ...] = (Purpose.MINE, Purpose.DWELLING, Purpose.BANK, "VISIT")
DWELL_LEVEL_W = (22, 18, 15, 13, 12, 10, 10)
TOWN_MIN_AREA = 150  # a town needs a real zone
RANDOM_SHARE = 0.7  # towns: random vs fixed split


@dataclass(frozen=True, slots=True)
class DrawSpec:
    zid: int
    terrain: str
    area: int
    player: bool = False
    gates: int = 0
    has_water: bool = False
    has_subterrain: bool = False


@dataclass(slots=True)
class ZoneDraw:
    """The identities one zone places, in placement order: its town, its mines (the economy
    pair first), then its attractions (dwellings, banks, visitables)."""

    total: int = 0
    town: Identity | None = None
    mines: list[Identity] = field(default_factory=list)
    attractions: list[tuple[str, Identity]] = field(default_factory=list)
    pools: dict[str, list[Identity]] = field(default_factory=dict)


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


@final
class ZoneDrawer:
    def __init__(
        self, catalog: Catalog, spec: DrawSpec, st: TerrainStats, ledger: Ledger, seed: int
    ) -> None:
        self.catalog = catalog
        self.spec = spec
        self.st = st
        self.ledger = ledger
        self.rng = random.Random(seed ^ (spec.zid * 40503) ^ DRAW_SALT)
        self.dens = density(st)
        self.used_anims: set[str] = set()
        self.pools: dict[str, list[Identity]] = {}

    def draw(self) -> ZoneDraw:
        spec, rng = self.spec, self.rng
        total = stoch_round(rng, spec.area * sum(self.dens.get(p, 0.0) for p in COUNTED))
        forced = spec.gates + (TOWN_SLOTS if spec.player else 0)
        town = spec.player or self._neutral_town(total - forced)
        if town and not spec.player:
            forced += TOWN_SLOTS
            self.ledger.towns += 1
        shares = self._split(max(0, total - forced))
        out = ZoneDraw(total=total, pools=self.pools)
        if town:
            out.town = self._town()
        out.mines = self._mines(shares[Purpose.MINE] + (2 if town else 0))
        out.attractions = [
            *self._dwellings(shares[Purpose.DWELLING]),
            *self._banks(shares[Purpose.BANK]),
            *self._visits(shares["VISIT"]),
        ]
        return out

    def _neutral_town(self, room: int) -> bool:
        spec = self.spec
        if spec.area < TOWN_MIN_AREA or room < TOWN_SLOTS:
            return False
        return self.rng.random() < self.dens.get(Purpose.TOWN, 0.0) * spec.area

    def _split(self, rest: int) -> dict[str, int]:
        shares = dict.fromkeys(MIX, 0)
        weights = [
            self.dens.get(Purpose.MINE, 0.0),
            self.dens.get(Purpose.DWELLING, 0.0),
            self.dens.get(Purpose.BANK, 0.0),
            sum(self.dens.get(p, 0.0) for p in VISIT_PURPOSES),
        ]
        if rest <= 0 or sum(weights) <= 0:
            return shares
        for kind in self.rng.choices(MIX, weights=weights, k=rest):
            shares[kind] += 1
        return shares

    def _pick(self, pool: Iterable[Identity], purpose: str) -> Identity | None:
        w = self.st.anim_w.get(purpose, {})
        ident = pick_kind(
            pool,
            lambda i: cast(
                float,
                (w.get(i.animation.lower(), 0) ** 0.5 + 0.3)
                * (0.05 if i.animation.lower() in self.used_anims else 1.0),
            ),
            self.rng,
        )
        if ident is not None:
            self.used_anims.add(ident.animation.lower())
        return ident

    def _town(self) -> Identity | None:
        if self.spec.player or self.rng.random() < RANDOM_SHARE:
            return self.catalog.identity_of(RND_TOWN)
        return self._pick(self.catalog.candidates(Purpose.TOWN, self.spec.terrain), Purpose.TOWN)

    def _take(self, ids: list[Identity], res: str, used: set[str], out: list[Identity]) -> None:
        ident = self._pick(ids, Purpose.MINE)
        if ident is not None:
            out.append(ident)
        used.add(res)
        self.ledger.missing.discard(res)
        if res == "goldMine":
            self.ledger.gold += 1

    def _resource(self, rest: Mapping[str, list[Identity]], mine_w: Mapping[str, int]) -> str:
        missing = self.ledger.missing & set(rest)
        keys = sorted(missing) if missing else sorted(rest)
        rw = [sum(mine_w.get(i.animation.lower(), 0) for i in rest[k]) + 0.2 for k in keys]
        return self.rng.choices(keys, weights=rw, k=1)[0]

    def _mines(self, n: int) -> list[Identity]:
        mine_w = self.st.anim_w.get(Purpose.MINE, {})
        mines = {
            res: mine_variants(ids, mine_w)
            for res, ids in self.catalog.mines_by_resource(self.spec.terrain).items()
        }
        out: list[Identity] = []
        used: set[str] = set()
        if n >= 2:
            for res in ECONOMY:
                if mines.get(res):
                    self._take(mines[res], res, used, out)
        while len(out) < n:
            rest = rest_mines(mines, used, self.ledger)
            if not rest:
                break
            res = self._resource(rest, mine_w)
            self._take(rest[res], res, used, out)
        return out

    def _keep_pool(self, purpose: str, pool: Iterable[Identity]) -> list[Identity]:
        kept = self.pools.setdefault(purpose, [])
        for ident in pool:
            if ident not in kept:
                kept.append(ident)
        return kept

    def _dwellings(self, n: int) -> list[tuple[str, Identity]]:
        rng = self.rng
        out: list[tuple[str, Identity]] = []
        if n:
            _ = self._keep_pool(
                Purpose.DWELLING, [self.catalog.identity_of(a) for a in RND_DWELL_L]
            )
            _ = self._keep_pool(
                Purpose.DWELLING, self.catalog.candidates(Purpose.DWELLING, self.spec.terrain)
            )
        for _ in range(n):
            ident: Identity | None
            if rng.random() < 0.8:
                anim = (
                    RND_DWELL
                    if rng.random() < 0.3
                    else rng.choices(RND_DWELL_L, weights=DWELL_LEVEL_W, k=1)[0]
                )
                ident = self.catalog.identity_of(anim)
            else:
                ident = self._pick(self.pools[Purpose.DWELLING], Purpose.DWELLING)
            if ident:
                out.append((Purpose.DWELLING, ident))
        return out

    def _banks(self, n: int) -> list[tuple[str, Identity]]:
        out: list[tuple[str, Identity]] = []
        for _ in range(n):
            ident = self._pick(
                self._keep_pool(
                    Purpose.BANK, self.catalog.candidates(Purpose.BANK, self.spec.terrain)
                ),
                Purpose.BANK,
            )
            if ident:
                out.append((Purpose.BANK, ident))
        return out

    def _visits(self, n: int) -> list[tuple[str, Identity]]:
        spec = self.spec
        vw = [self.st.counts.get(p, 0) + 0.2 for p in VISIT_PURPOSES]
        out: list[tuple[str, Identity]] = []
        for _ in range(n):
            p = self.rng.choices(VISIT_PURPOSES, weights=vw, k=1)[0]
            pool = (
                info_pool(self.catalog, spec.terrain, spec.has_water, spec.has_subterrain)
                if p == Purpose.INFO
                else self.catalog.candidates(p, spec.terrain)
            )
            ident = self._pick(self._keep_pool(p, pool), p)
            if ident:
                out.append((p, ident))
        return out
