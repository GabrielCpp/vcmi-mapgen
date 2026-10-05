"""SetsStep: deals complete artifact sets onto the prize slots the cut-off places held back."""

from __future__ import annotations

import random
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, MapState
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.placement.ways import kept_rules
from vcmi_mapgen.core.planning.pricing import CutoffPlace
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import PromisedWays
from vcmi_mapgen.core.steps.loot.result import LootResult
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.sets.deal import (
    Dealer,
    deal_sets,
    dealable,
    set_quota,
    tiers_of,
    top_slots,
)
from vcmi_mapgen.core.steps.sets.result import PlacedSet, SetsResult
from vcmi_mapgen.core.steps.sets.slots import price_slots
from vcmi_mapgen.core.steps.sets.stand import Board, stand_all
from vcmi_mapgen.core.steps.treasure.result import TreasureResult


def _held(*places: dict[int, dict[int, CutoffPlace]]) -> list[HeldPrize]:
    return [
        h
        for by_level in places
        for level in by_level.values()
        for p in level.values()
        for h in p.held
    ]


@final
class SetsStep(PipelineStep):
    """Combined artifacts. The treasure, portal and loot steps each hold one prize slot back
    per place. This step prices every slot by the effort from its nearest home, deals whole
    sets onto the slots in the top two bands, one part per place and round-robin over the
    homes, and fills every slot no set took with the artifact its place drew.

    Config:
        priors      The corpus priors; the step reads the effort priors and the level-0
                    gameplay statistics.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (the level claims), and the held slots of ``TreasureResult``,
    ``PortalResult`` and ``LootResult`` when present.

    Produces: appends the set parts and fallback prizes to ``map_state.objs``, and provides
    ``SetsResult``.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size
        self._zones = ZoneIndex()
        self._held: list[HeldPrize] = []
        self._ctx = ProviderRegistry()
        self._ways = PromisedWays()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._ways = ctx.get(PromisedWays, PromisedWays())
        self._zones = ctx.require(ZoneIndex)
        treasure = ctx.get(TreasureResult, TreasureResult()).places
        portal = ctx.get(PortalResult, PortalResult()).places
        self._held = [*_held(treasure, portal), *ctx.get(LootResult, LootResult()).held]

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        rng = random.Random(self.seed ^ 0x5E75)
        slots = price_slots(catalog, map_state, self._held, self.priors.effort)
        water = any(t.is_water for g in map_state.terrain.values() for row in g for t in row)
        quota = set_quota(len(map_state.terrain), self.size)
        dealer = Dealer(dealable(catalog, water), tiers_of(catalog), quota)
        deals = deal_sets(dealer, slots, rng)
        stood = stand_all(catalog, self._board(map_state), deals, self._held, rng)
        map_state.add_objs(stood.objs())
        filled = sum(o is not None for o in stood.fallbacks)
        empty = len(stood.fallbacks) - filled
        names = [d.name for d, _ in stood.sets]
        found = f"slots={len(slots)} top={len(top_slots(slots))} filled={filled} empty={empty}"
        print(f"  sets: {len(names)}/{quota} {names} {found}")
        placed = [
            PlacedSet(d.name, tuple(parts), tuple(s.band for s, _ in d.parts))
            for d, parts in stood.sets
        ]
        self._ctx.provide(SetsResult(placed, filled, empty))

    def _board(self, map_state: MapState) -> Board:
        by_level = map_state.objs_by_level(map_state.terrain)
        covers: dict[int, CoverIndex] = {}
        for level, objs in by_level.items():
            held = {h.tile for h in self._held if h.level == level}
            claims = self._zones.claims.get(level, frozenset()) - held
            covers[level] = CoverIndex(
                objs, claims, kept_rules(map_state, level, self._ways.on(level))
            )
        return Board(covers, self.priors.gameplay[0], (self.size, self.size))
