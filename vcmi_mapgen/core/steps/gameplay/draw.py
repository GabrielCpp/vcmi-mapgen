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
from typing import final

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.steps.gameplay.mines import (
    RANDOM_SHARE,
    RND_DWELL,
    RND_DWELL_L,
    RND_TOWN,
    TOWN_MIN_AREA,
    VISIT_PURPOSES,
    Ledger,
    TerrainStats,
    info_pool,
    mine_variants,
    rest_mines,
)

DRAW_SALT = 0x5EED
TOWN_SLOTS = 3
COUNTED = ("TOWN", "MINE", "DWELLING", "BANK", *VISIT_PURPOSES, "TRANSPORT", "WATER_TRANSPORT")
MIX: tuple[str, ...] = ("MINE", "DWELLING", "BANK", "VISIT")
ECONOMY = ("sawmill", "orePit")
DWELL_LEVEL_W = (22, 18, 15, 13, 12, 10, 10)


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


def stoch_round(rng: random.Random, x: float) -> int:
    return int(x) + (1 if rng.random() < x - int(x) else 0)


def density(st: TerrainStats) -> dict[str, float]:
    return {p: c / max(st.tiles, 1) for p, c in st.counts.items()}


@final
class ZoneDrawer:
    def __init__(self, spec: DrawSpec, st: TerrainStats, ledger: Ledger, seed: int) -> None:
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
        out.mines = self._mines(shares["MINE"] + (2 if town else 0))
        out.attractions = [
            *self._dwellings(shares["DWELLING"]),
            *self._banks(shares["BANK"]),
            *self._visits(shares["VISIT"]),
        ]
        return out

    def _neutral_town(self, room: int) -> bool:
        spec = self.spec
        if spec.area < TOWN_MIN_AREA or room < TOWN_SLOTS:
            return False
        return self.rng.random() < self.dens.get("TOWN", 0.0) * spec.area

    def _split(self, rest: int) -> dict[str, int]:
        shares = dict.fromkeys(MIX, 0)
        weights = [
            self.dens.get("MINE", 0.0),
            self.dens.get("DWELLING", 0.0),
            self.dens.get("BANK", 0.0),
            sum(self.dens.get(p, 0.0) for p in VISIT_PURPOSES),
        ]
        if rest <= 0 or sum(weights) <= 0:
            return shares
        for kind in self.rng.choices(MIX, weights=weights, k=rest):
            shares[kind] += 1
        return shares

    def _pick(self, pool: Iterable[Identity], purpose: str) -> Identity | None:
        cands = sorted(
            (i for i in pool if "random" not in (i.type or "").lower()),
            key=lambda i: i.animation,
        )
        if not cands:
            return None
        w = self.st.anim_w.get(purpose, {})
        weights = [
            (w.get(i.animation.lower(), 0) ** 0.5 + 0.3)
            * (0.05 if i.animation.lower() in self.used_anims else 1.0)
            for i in cands
        ]
        ident = self.rng.choices(cands, weights=weights, k=1)[0]
        self.used_anims.add(ident.animation.lower())
        return ident

    def _town(self) -> Identity | None:
        if self.spec.player or self.rng.random() < RANDOM_SHARE:
            return ON.identity_of(RND_TOWN)
        return self._pick(ON.pool("TOWN", self.spec.terrain), "TOWN")

    def _take(self, ids: list[Identity], res: str, used: set[str], out: list[Identity]) -> None:
        ident = self._pick(ids, "MINE")
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
        mine_w = self.st.anim_w.get("MINE", {})
        mines = {
            res: mine_variants(ids, mine_w)
            for res, ids in ON.mines_by_resource(self.spec.terrain).items()
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
            _ = self._keep_pool("DWELLING", [ON.identity_of(a) for a in RND_DWELL_L])
            _ = self._keep_pool("DWELLING", ON.pool("DWELLING", self.spec.terrain))
        for _ in range(n):
            ident: Identity | None
            if rng.random() < 0.8:
                anim = (
                    RND_DWELL
                    if rng.random() < 0.3
                    else rng.choices(RND_DWELL_L, weights=DWELL_LEVEL_W, k=1)[0]
                )
                ident = ON.identity_of(anim)
            else:
                ident = self._pick(self.pools["DWELLING"], "DWELLING")
            if ident:
                out.append(("DWELLING", ident))
        return out

    def _banks(self, n: int) -> list[tuple[str, Identity]]:
        out: list[tuple[str, Identity]] = []
        for _ in range(n):
            ident = self._pick(self._keep_pool("BANK", ON.pool("BANK", self.spec.terrain)), "BANK")
            if ident:
                out.append(("BANK", ident))
        return out

    def _visits(self, n: int) -> list[tuple[str, Identity]]:
        spec = self.spec
        vw = [self.st.counts.get(p, 0) + 0.2 for p in VISIT_PURPOSES]
        out: list[tuple[str, Identity]] = []
        for _ in range(n):
            p = self.rng.choices(VISIT_PURPOSES, weights=vw, k=1)[0]
            pool = (
                info_pool(spec.terrain, spec.has_water, spec.has_subterrain)
                if p == "INFO"
                else ON.pool(p, spec.terrain)
            )
            ident = self._pick(self._keep_pool(p, pool), p)
            if ident:
                out.append((p, ident))
        return out
