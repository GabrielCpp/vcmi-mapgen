"""GatedStep: seals small one-passage zones behind a Border Gate or a monolith pair."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import land_reach
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.start_room import start_rules
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.guarding import prize_guard
from vcmi_mapgen.core.planning.pricing import homes
from vcmi_mapgen.core.planning.zone_index import build_zone_index
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, GateResult
from vcmi_mapgen.core.steps.gated.loot_zones import mark_loot_zones, walk_targets
from vcmi_mapgen.core.steps.gated.placer import GatedLevel, place_gated_zones
from vcmi_mapgen.core.steps.gated.result import GatedResult


def _reached(map_state: MapState, gate_xy: set[Tile]) -> dict[int, frozenset[Tile]] | None:
    starts = [(h.level, (h.x, h.y)) for h in homes(map_state)]
    if not starts:
        return None
    found = land_reach(map_state.terrain, gate_xy, starts)
    return {lvl: frozenset((x, y) for x, y, at in found if at == lvl) for lvl in map_state.terrain}


def _report_loot(level: int, n_loot: int, loot_zids: set[int]) -> None:
    if n_loot:
        zid_str = ", ".join(str(z) for z in sorted(loot_zids))
        print(
            f"  L{level} loot zones: {n_loot} access pair(s) placed "
            + f"(1 gate+key, {n_loot - 1} sealed+monolith) zones=[{zid_str}]"
            if n_loot > 1
            else f"  L{level} loot zones: 1 gate+key pair placed zones=[{zid_str}]"
        )


@final
class GatedStep(PipelineStep):
    """Loot-zone access: each small zone with a single passage is sealed with blocking
    decoration, and its only way in becomes a Border Gate with a guarded Keymaster outside,
    or a monolith pair with a guarded partner outside.

    Config:
        priors      The corpus priors; the step reads the level-0 gameplay statistics and
                    each level's place content.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZonePlan`` (each zone's plan), ``GameplayResult`` (each zone after
    placement and the recomputed seaport landings), ``GateResult`` (the subterranean gates a
    hero walks through between levels) and the ``ContentPlan`` when present, whose hops pick
    the level of each partner guard from the corpus spread. A zone no home reaches on foot
    is never sealed and never holds a partner.

    Produces: appends the gates, monoliths, partners, guards and seals to ``map_state.objs``,
    and provides ``ZoneIndex`` and ``GatedResult``.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._plan = ZonePlan({}, ())
        self._gameplay = GameplayResult({}, {}, {})
        self._content = ContentPlan()
        self._gate_xy: set[Tile] = set()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._plan = ctx.require(ZonePlan)
        self._gameplay = ctx.require(GameplayResult)
        self._content = ctx.get(ContentPlan, ContentPlan())
        self._gate_xy = {(o.x, o.y) for o in ctx.require(GateResult).gate_objs if o.level == 0}

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        index = build_zone_index(self._plan, self._gameplay.zones, self._gameplay.landings)
        by_level = map_state.objs_by_level(index.zone_records)
        result = GatedResult()
        reached = _reached(map_state, self._gate_xy)
        for level, zone_records in index.zone_records.items():
            new, n, access, claims = place_gated_zones(
                catalog,
                GatedLevel(
                    zone_records,
                    by_level[level],
                    self.priors.gameplay[0],
                    start_rules(map_state, level),
                    map_state.terrain.get(level, ()),
                    prize_guard(self.priors.places, self._content, level),
                    None if reached is None else reached[level],
                ),
                seed=self.seed,
                bounds=(self.size, self.size),
            )
            for o in new:
                o.level = level
            index.zone_records[level] = mark_loot_zones(zone_records, access)
            index.targets[level][:] = walk_targets(index.targets[level], new, zone_records, access)
            result.access[level] = access
            index.claims[level] = claims
            self.objs.extend(new)
            _report_loot(level, n, set(access))
        map_state.add_objs(self.objs)
        self._ctx.provide(index)
        self._ctx.provide(result)
