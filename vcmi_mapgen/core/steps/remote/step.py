"""RemoteStep: a landmark in every run of free land far from every object worth the walk."""

from __future__ import annotations

from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.keep_out import KeepOutRule
from vcmi_mapgen.core.placement.site import LevelField, SiteZone
from vcmi_mapgen.core.placement.ways import kept_rules
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.planning.zone_plan import ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, PromisedWays
from vcmi_mapgen.core.steps.remote.fill import RemoteLevel, approaches, fill_level, landings


@final
class RemoteStep(PipelineStep):
    """After every reward and free pile, find the runs of free land farther than the corpus
    remote distance from every object worth the walk, and stand a landmark in each: an
    abandoned mine, a stat building or a dwelling, down to a pickup.

    Config:
        priors     The corpus priors; the step reads the remote distance and the gameplay
                   statistics per level.
        seed       RNG seed.
        size       Map side length in tiles (square).

    inject(ctx): ``ZonePlan``, ``GameplayResult``, the ``ZoneIndex`` claims and the
    ``PromisedWays`` when present.

    Produces: appends each landmark and its guard to ``map_state.objs``.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors: Priors = priors
        self.seed: int = seed
        self.size: int = size
        self._plan: ZonePlan = ZonePlan({}, ())
        self._gameplay: GameplayResult = GameplayResult({}, {}, {})
        self._zones: ZoneIndex = ZoneIndex()
        self._ways: PromisedWays = PromisedWays()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._plan = ctx.require(ZonePlan)
        self._gameplay = ctx.require(GameplayResult)
        self._zones = ctx.get(ZoneIndex, ZoneIndex())
        self._ways = ctx.get(PromisedWays, PromisedWays())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        new: list[PlacedObject] = []
        for level in sorted(self._plan.levels):
            fill = fill_level(catalog, self._level(map_state, level), self.seed)
            new.extend(fill.objs)
            for line in fill.log:
                print(line)
        map_state.add_objs(new)

    def _level(self, map_state: MapState, level: int) -> RemoteLevel:
        grid = map_state.terrain[level]
        objs = [o for o in map_state.objs if o.level == level]
        claims = self._zones.claims.get(level, frozenset())
        rules = (*kept_rules(map_state, level, self._ways.on(level)), KeepOutRule(claims))
        lf = LevelField.build(level, grid, objs, rules=rules)
        zones: dict[int, SiteZone] = {}
        for zid, zone in self._plan.levels[level].zones.items():
            pz = self._gameplay.zones.get(level, {}).get(zid)
            if pz is None:
                continue
            st = self.priors.gameplay[level][zone.terrain]
            open_set = pz.open_set - lf.occupied
            passable = pz.passable - lf.unwalkable
            prot = pz.prot | landings(passable, pz.prot, grid, lf.unwalkable)
            zones[zid] = SiteZone(
                zone.terrain, st, zone.ts, zone.ent_bands, prot, open_set, passable
            )
        zone_of = {t: zid for zid, z in self._plan.levels[level].zones.items() for t in z.ts}
        kept = approaches(objs, lf.unwalkable, len(grid))
        far = self.priors.remote.at(self.size)
        return RemoteLevel(level, grid, objs, zone_of, zones, lf, kept, claims, far)
