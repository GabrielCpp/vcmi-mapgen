"""CompensationStep: a guarded artifact prize for each player who claims first far less value
than the best player."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast, override

import numpy as np

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.artifact import ArtifactTier
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.planning.guarding import tier_guard
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.claimed import claimed, claims_of, owner_maps
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.reading.routes import Spot, route_map
from vcmi_mapgen.core.reading.value import ARTIFACT_VALUE
from vcmi_mapgen.core.steps.compensation.prize import BAR, deficits, prize_ground, prize_tier
from vcmi_mapgen.core.steps.compensation.result import CompensationResult, Prize
from vcmi_mapgen.core.steps.compensation.stand import PrizeStand


class CompensationStep(PipelineStep):
    """After every reward is placed, read the value each player claims first within each
    horizon of ``BAR``. A player below the bar's share of the best player's value gets one
    artifact worth about the gap, behind the weakest guard its tier allows, on a tile it
    reaches first: within the shortest horizon where one fits, else the longest. Players
    lacking the most are served first.

    Config:
        priors     The corpus priors; the step reads the guard toll in hero-days.

    Produces: appends each prize and its guard to ``map_state.objs`` and provides a
    ``CompensationResult``.
    """

    def __init__(self, priors: Priors) -> None:
        self.priors: Priors = priors
        self._ctx: ProviderRegistry | None = None

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        result = self._compensate(catalog, map_state)
        if self._ctx is not None:
            self._ctx.provide(result)

    def _compensate(self, catalog: Catalog, map_state: MapState) -> CompensationResult:
        route = route_map(catalog, map_state)
        maps = owner_maps(catalog, map_state, owners_of(map_state), self.priors.effort.toll, route)
        if len(maps) < 2:
            return CompensationResult({}, (), {})
        claims = claims_of(catalog, map_state, maps)
        before = {h: claimed(claims, h) for h in BAR}
        lacking = deficits(before, BAR)
        stand = PrizeStand(catalog, map_state, route)
        ground = stand.ground()
        prizes: list[Prize] = []
        for player in sorted(range(len(maps)), key=lambda p: (-lacking[p], p)):
            tier = prize_tier(lacking[player])
            if tier is None:
                continue
            prize = _stand(stand, maps, ground, player, tier)
            if prize is None:
                print(
                    f"compensation: P{player} lacks {lacking[player]} gold and finds no {tier} spot"
                )
                continue
            prizes.append(prize)
            at = f"L{prize.spot.level} ({prize.spot.x},{prize.spot.y})"
            gets = f"a {tier} behind a level {prize.guard} guard at {at} in {prize.days} days"
            print(f"compensation: P{player} lacks {lacking[player]} gold, gets {gets}")
        map_state.add_objs([o for p in stand.placed for o in p])
        after = _after(before, prizes)
        behind = {p: d for p, d in enumerate(deficits(after, BAR)) if d > 0}
        return CompensationResult(before, tuple(prizes), behind)


def _stand(
    stand: PrizeStand,
    maps: Sequence[EffortMap],
    ground: Sequence[Spot],
    player: int,
    tier: ArtifactTier,
) -> Prize | None:
    guard = tier_guard(tier)
    totals = np.stack([em.visits(ground, guard)[guard] for em in maps])
    art, keeper = stand.catalog.random_artifact(tier), stand.catalog.guard(guard)
    index = {s: i for i, s in enumerate(ground)}
    for within in sorted(BAR):
        mine = prize_ground(totals, player, within)
        spots = [s for s, ok in zip(ground, cast(list[bool], mine.tolist()), strict=True) if ok]
        for spot in stand.order(spots):
            if stand.place(spot, art, (keeper, guard), maps):
                return Prize(player, tier, guard, spot, cast(int, totals.item(player, index[spot])))
    return None


def _after(
    before: Mapping[int, tuple[int, ...]], prizes: Sequence[Prize]
) -> dict[int, tuple[int, ...]]:
    out = {h: list(v) for h, v in before.items()}
    for p in prizes:
        for h, values in out.items():
            if p.days <= h:
                values[p.player] += ARTIFACT_VALUE[p.tier]
    return {h: tuple(v) for h, v in out.items()}
