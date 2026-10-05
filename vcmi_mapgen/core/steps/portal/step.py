"""PortalStep: links every cut-off zone to the start zone with a portal pair."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.ways import kept_rules
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.guarding import prize_guard
from vcmi_mapgen.core.planning.pricing import CutoffPlace, effort_with, prize_count
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import (
    GameplayResult,
    GateResult,
    PromisedWays,
    TownsIndex,
)
from vcmi_mapgen.core.steps.portal import rescue as RS
from vcmi_mapgen.core.steps.portal.hoard import HoardPricing, fill_hoards
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.treasure.result import TreasureResult


def _find_start(
    player_zids: Sequence[tuple[int, int]],
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    town_of_zone: Mapping[int, Mapping[int, PlacedObject]],
) -> tuple[int, Tile] | None:
    """Return (level, (x, y)) for the first player town, or centroid of the
    largest surface land zone when there are no players."""
    for lvl, zid in player_zids:
        t = town_of_zone.get(lvl, {}).get(zid)
        if t is not None:
            return (lvl, (t.x, t.y))
    zones0 = zones_by_level.get(0, {})
    big = max(
        (z for z in zones0.values() if z.terrain_type.is_land),
        key=lambda z: z.area,
        default=None,
    )
    if big is not None:
        bx, by = big.centroid
        return (0, min(big.tiles_set, key=lambda t: ((t[0] - bx) ** 2 + (t[1] - by) ** 2, t)))
    return None


def _added(
    by_level: Mapping[int, Sequence[PlacedObject]], known: Sequence[PlacedObject]
) -> list[PlacedObject]:
    before = {id(o) for o in known}
    return [o for lvl in sorted(by_level) for o in by_level[lvl] if id(o) not in before]


@final
class PortalStep(PipelineStep):
    """Portal rescue: a zone the start cannot walk to and no earlier step priced gets a
    guarded portal pair, and prizes from the band of the effort to carry them home.

    Config:
        priors      The corpus priors; the step reads the level-0 gameplay statistics, the
                    effort priors and each level's place content.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (targets and claims, mutated in place), ``Segmentation``,
    ``TownsIndex`` (player_zids), ``GameplayResult`` (each zone's town), ``GateResult``, the
    ``TreasureResult`` places when present, which the step leaves alone, and the
    ``ContentPlan`` when present, whose hops pick each portal guard's level from the corpus
    spread.

    Produces: appends the portals, their guards and their prizes to ``map_state.objs`` and
    provides ``PortalResult``, each portal place's price and prizes.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self.log: list[str] = []
        self._ctx = ProviderRegistry()
        self._targets: dict[int, list[Tile]] = {}
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._claims: dict[int, frozenset[Tile]] = {}
        self._segmentation = Segmentation({}, {})
        self._town_of_zone: Mapping[int, Mapping[int, PlacedObject]] = {}
        self._player_zids: list[tuple[int, int]] = []
        self._gate_objs: list[PlacedObject] = []
        self._content = ContentPlan()
        self._priced: set[tuple[int, int]] = set()
        self._ways = PromisedWays()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._ways = ctx.get(PromisedWays, PromisedWays())
        zones = ctx.require(ZoneIndex)
        self._targets = zones.targets
        self._zone_records = zones.zone_records
        self._claims = zones.claims
        self._segmentation = ctx.require(Segmentation)
        self._town_of_zone = ctx.require(GameplayResult).town_of_zone
        self._player_zids = ctx.require(TownsIndex).player_zids
        self._gate_objs = ctx.require(GateResult).gate_objs
        self._content = ctx.get(ContentPlan, ContentPlan())
        places = ctx.get(TreasureResult, TreasureResult()).places
        self._priced = {(lvl, zid) for lvl, found in places.items() for zid in found}

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        grids = map_state.terrain
        by_level = map_state.objs_by_level(grids)
        covers = {
            lvl: CoverIndex(
                objs, self._claims.get(lvl, ()), kept_rules(map_state, lvl, self._ways.on(lvl))
            )
            for lvl, objs in by_level.items()
        }
        world = RS.PortalWorld(
            self.size,
            grids,
            self._segmentation.zones,
            by_level,
            self._targets,
            self._zone_records,
            covers,
            self.priors.gameplay[0],
            {lvl: prize_guard(self.priors.places, self._content, lvl) for lvl in grids},
        )
        start = _find_start(self._player_zids, self._segmentation.zones, self._town_of_zone)
        rescued: list[RS.Rescued] = []
        if start is not None:
            gate_xy = {(o.x, o.y) for o in self._gate_objs if o.level == 0}
            departure = RS.Departure(start, gate_xy, self._priced)
            rescued = RS.rescue_unreachable_zones(catalog, world, departure, self.seed)
        places = self._prizes(catalog, map_state, world, rescued)
        for lvl, cover in covers.items():
            self._claims[lvl] = frozenset(cover.claims)
        RS.check_reach(world)
        self.objs = _added(by_level, map_state.objs)
        map_state.add_objs(self.objs)
        if rescued:
            self.log.append(f"PortalStep: {len(rescued)} portal rescue(s) added")
        self._ctx.provide(PortalResult(self.log, places))

    def _prizes(
        self,
        catalog: Catalog,
        map_state: MapState,
        world: RS.PortalWorld,
        rescued: Sequence[RS.Rescued],
    ) -> dict[int, dict[int, CutoffPlace]]:
        if not rescued:
            return {}
        portals = _added(world.objs_by_level, map_state.objs)
        em = effort_with(catalog, map_state, self.priors.effort.toll, portals)
        counts = {lvl: prize_count(self.priors.places, lvl) for lvl in world.grids}
        pricing = HoardPricing(em, self.priors.effort, counts)
        return fill_hoards(catalog, world, rescued, pricing, self.seed)
