"""TreasureStep: fills every sealed loot zone with treasure."""

from __future__ import annotations

from collections.abc import Mapping
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import land_reach
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.placement.ways import kept_rules
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.guarding import prize_guard
from vcmi_mapgen.core.planning.pricing import (
    CutoffPlace,
    Opener,
    Price,
    effort_with,
    homes,
    prize_count,
)
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import GateResult, PromisedWays
from vcmi_mapgen.core.steps.gated.result import GatedResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.treasure.fill import LootFill, LootLevel, fill_loot_zones
from vcmi_mapgen.core.steps.treasure.islands import IslandFill, IslandLevel
from vcmi_mapgen.core.steps.treasure.price import price_places, prizes
from vcmi_mapgen.core.steps.treasure.result import TreasureResult


def _slot(held: Mapping[int, HeldPrize], zid: int) -> tuple[HeldPrize, ...]:
    return (held[zid],) if zid in held else ()


@final
class TreasureStep(PipelineStep):
    """Cut-off treasure. Loot zones get hero structures, artifacts, chests, scrolls and rare
    resources on the free tiles behind their gate or monolith. Islands, the land places a
    hero reaches only by boat, get guarded prizes by their size. Each place is priced by the
    effort a hero spends to reach it, and its artifact class is drawn from its band.

    Config:
        priors      The corpus priors; the step reads the level-0 gameplay statistics, the
                    effort priors and each level's place content.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (zone records, and the level claims it writes back),
    ``GatedResult``, ``Segmentation``, ``GateResult`` and the ``ContentPlan`` when present.

    Produces: appends the treasure to ``map_state.objs``, and provides ``TreasureResult``,
    each loot zone's and island's price and prizes.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._zones = ZoneIndex()
        self._gated = GatedResult()
        self._segmentation = Segmentation({}, {})
        self._gate_objs: list[PlacedObject] = []
        self._content = ContentPlan()
        self._ctx = ProviderRegistry()
        self._ways = PromisedWays()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._ways = ctx.get(PromisedWays, PromisedWays())
        self._zones = ctx.require(ZoneIndex)
        self._gated = ctx.require(GatedResult)
        self._segmentation = ctx.require(Segmentation)
        self._gate_objs = ctx.require(GateResult).gate_objs
        self._content = ctx.get(ContentPlan, ContentPlan())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        toll = self.priors.effort.toll
        fills = [self._islands(map_state, level) for level in sorted(map_state.terrain)]
        reached = land_reach(map_state.terrain, self._gate_xy(), self._starts(map_state))
        bare = effort_with(catalog, map_state, toll)
        guards = [g for f in fills for g in f.guard(catalog, bare, reached)]
        em = effort_with(catalog, map_state, toll, guards)
        places: dict[int, dict[int, CutoffPlace]] = {level: {} for level in map_state.terrain}
        for f in fills:
            found, kept = f.fill(catalog, em, self.priors.effort)
            places[f.lvl.level].update(found)
            self.objs.extend(kept)
            self._zones.claims[f.lvl.level] = frozenset(f.cover.claims)
        prices = price_places(em, self._gated.access, self.priors.effort)
        for level in self._gated.access:
            level_objs = [o for o in [*map_state.objs, *self.objs] if o.level == level]
            fill = self._fill_level(catalog, level, level_objs, map_state, prices[level])
            new = fill.objs
            for o in new:
                o.level = level
            self.objs.extend(new)
            found = prizes(self._zones.zone_records[level], new)
            gated = {
                z: CutoffPlace(Opener.GATE, p, found[z], _slot(fill.held, z))
                for z, p in prices[level].items()
            }
            places.setdefault(level, {}).update(gated)
        map_state.add_objs(self.objs)
        self._ctx.provide(TreasureResult(places))

    def _gate_xy(self) -> set[tuple[int, int]]:
        return {(o.x, o.y) for o in self._gate_objs if o.level == 0}

    @staticmethod
    def _starts(map_state: MapState) -> list[tuple[int, tuple[int, int]]]:
        return [(h.level, (h.x, h.y)) for h in homes(map_state)]

    def _islands(self, map_state: MapState, level: int) -> IslandFill:
        objs = [o for o in map_state.objs if o.level == level]
        rules = kept_rules(map_state, level, self._ways.on(level))
        lvl = IslandLevel(
            level,
            self._segmentation.zones.get(level, {}),
            self._zones.zone_records.get(level, []),
            self._gated.access.get(level, {}),
            objs,
            self.priors.gameplay[0],
            prize_guard(self.priors.places, self._content, level),
            prize_count(self.priors.places, level),
            self._zones.claims.get(level, frozenset()),
            rules,
        )
        cover = CoverIndex(objs, lvl.claims, rules)
        return IslandFill(lvl, cover, self.seed, (self.size, self.size))

    def _fill_level(
        self,
        catalog: Catalog,
        level: int,
        level_objs: list[PlacedObject],
        map_state: MapState,
        prices: dict[int, Price],
    ) -> LootFill:
        footprints = {zid: acc.footprint for zid, acc in self._gated.access[level].items()}
        offers = {zid: self.priors.effort.offer(p.band) for zid, p in prices.items()}
        claims = self._zones.claims.get(level, frozenset())
        loot = LootLevel(
            self._zones.zone_records[level],
            footprints,
            offers,
            level_objs,
            self.priors.gameplay[0],
            claims,
            kept_rules(map_state, level, self._ways.on(level)),
            level,
        )
        fill = fill_loot_zones(catalog, loot, self.seed, (self.size, self.size))
        self._zones.claims[level] = fill.claims
        return fill
