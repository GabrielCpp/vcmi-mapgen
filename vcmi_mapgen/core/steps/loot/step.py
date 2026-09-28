"""LootStep: seer-hut quests and guarded pocket caches over the finished level."""

from __future__ import annotations

import collections
from dataclasses import replace
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.pockets import Pockets, find_pockets
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.rules import TerrainGate
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.border.result import BorderResult
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.loot import pickups as PK
from vcmi_mapgen.core.steps.loot import quests as QU
from vcmi_mapgen.core.steps.loot.result import LootResult


def _precompute_pockets(
    zone_records: list[ZoneRecord],
) -> tuple[dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]], set[Tile]]:
    _global_true_pkt: set[Tile] = set()
    for _zr_pkt in zone_records:
        _global_true_pkt |= _zr_pkt.passable
    _raw_pkt = find_pockets(_global_true_pkt)
    _pocket_tiles_pkt: set[Tile] = set()
    for _g_pkt, (_pt_pkt, _mf_pkt) in _raw_pkt.items():
        if len(_pt_pkt) >= 3:
            _pocket_tiles_pkt |= set(_pt_pkt)
    return _raw_pkt, _pocket_tiles_pkt


@final
class LootStep(PipelineStep):
    """Content that depends on the finished walkable field: seer-hut quests and guarded
    pocket caches.

    Config:
        priors      The corpus priors; the step reads the level-0 gameplay statistics.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (targets/zone_records), ``TownsIndex`` (player_zids),
    ``BorderResult`` (``guard_tiles`` per level, taken off each zone's open tiles).

    Produces: appends its objects to ``map_state.objs`` and provides ``LootResult``.
    """

    def __init__(self, priors: Priors, seed: int = 3, size: int = 72) -> None:
        self.priors = priors
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._targets: dict[int, list[Tile]] = {}
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._claims: dict[int, frozenset[Tile]] = {}
        self._player_zids: list[tuple[int, int]] = []
        self._guard_tiles: dict[int, frozenset[Tile]] = {}

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        zones = ctx.require(ZoneIndex)
        self._targets = zones.targets
        self._zone_records = zones.zone_records
        self._claims = zones.claims
        self._player_zids = ctx.require(TownsIndex).player_zids
        self._guard_tiles = dict(ctx.require(BorderResult).guard_tiles)

    def _place_level_loot(
        self,
        catalog: Catalog,
        level: int,
        objs: list[PlacedObject],
        seerhut_artifacts: set[str],
        home_zids: set[int],
    ) -> tuple[list[PlacedObject], dict[Tile, float]]:
        """Seer-hut quests and guarded pocket caches for ONE level. ``objs`` is the level's
        existing objects, read only. Returns (new_objs, pocket_depth_by_tile)."""
        size, seed = self.size, self.seed
        targets = self._targets[level]
        border_guards = self._guard_tiles.get(level, frozenset[Tile]())
        zone_records = [
            replace(zr, open_set=zr.open_set - border_guards) for zr in self._zone_records[level]
        ]
        _raw_pkt, _pocket_tiles_pkt = _precompute_pockets(zone_records)
        cover = CoverIndex(objs, self._claims.get(level, ()))
        qobjs, n_quests = QU.place_seer_hut_quests(
            catalog,
            zone_records,
            seed=seed,
            bounds=(size, size),
            context=QU.SeerHutContext(
                self.priors.gameplay[0],
                pocket_tiles=_pocket_tiles_pkt,
                existing_objs=objs,
                used_artifacts=seerhut_artifacts,
                cover=cover,
            ),
        )
        targets.extend((o.x, o.y) for o in qobjs)
        if n_quests:
            print(f"  L{level} seer hut quests: {n_quests}")

        cobjs, n_pockets, pocket_depth_by_tile = PK.place_pocket_caches(
            catalog,
            zone_records,
            seed=seed,
            bounds=(size, size),
            context=PK.PocketContext(
                self.priors.gameplay[0],
                border_guards=border_guards,
                precomputed_pockets=_raw_pkt,
                existing_objs=[*objs, *qobjs],
                home_zids=home_zids,
                cover=cover,
            ),
        )
        targets.extend((o.x, o.y) for o in cobjs)
        self._claims[level] = frozenset(cover.claims)
        ck = collections.Counter(o.purpose for o in cobjs)
        print(
            f"  L{level} pockets: {n_pockets} found, cache res={ck.get('RESOURCE_PILE', 0)} "
            + f"art={ck.get('REWARD_PICKUP', 0)} guard={ck.get('GUARD', 0)}"
        )
        return [*qobjs, *cobjs], pocket_depth_by_tile

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        objs_by_level = map_state.objs_by_level(self._zone_records)

        seerhut_artifacts: set[str] = set()
        pockets_by_level: Pockets = {}
        for level in sorted(objs_by_level):
            home_zids = {zid for lvl, zid in self._player_zids if lvl == level}
            new_objs, depth = self._place_level_loot(
                catalog, level, objs_by_level[level], seerhut_artifacts, home_zids
            )
            for o in new_objs:
                o.level = level
            self.objs.extend(new_objs)
            pockets_by_level[level] = depth

        map_state.add_objs(self.objs, TerrainGate(catalog))
        self._ctx.provide(LootResult(pockets=pockets_by_level))
