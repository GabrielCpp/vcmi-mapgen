"""LootStep: seer-hut quests and guarded pocket caches over the finished level."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.core.model import MapState, PlacedObject, Pockets, Tile, ZoneRecord
from vcmi_mapgen.core.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.core.steps.gameplay.step import TownsIndex
from vcmi_mapgen.core.steps.loot import caches as CA
from vcmi_mapgen.core.steps.zone_index import ZoneIndex
from vcmi_mapgen.kit.topology import find_pockets
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.validate import TerrainGate


@dataclass
class LootResult:
    """Pocket geometry for PocketOverlay (level -> {tile: normalized depth 0..1}). Disposable
    analysis, not a map fact, so it is not a MapState field."""

    pockets: Pockets = field(default_factory=dict)


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
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (targets/zone_records), ``TownsIndex`` (player_zids),
    the shared ``PlacementWorkspace`` (``guard_tiles`` per level).

    Produces: appends its objects to ``map_state.objs`` and provides ``LootResult``.
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed = seed
        self.size = size
        self.objs: list[PlacedObject] = []
        self._ctx = ProviderRegistry()
        self._targets: dict[int, list[Tile]] = {}
        self._zone_records: dict[int, list[ZoneRecord]] = {}
        self._player_zids: list[tuple[int, int]] = []
        self._workspace = PlacementWorkspace()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        zones = ctx.require(ZoneIndex)
        self._targets = zones.targets
        self._zone_records = zones.zone_records
        self._player_zids = ctx.require(TownsIndex).player_zids
        self._workspace = ctx.require(PlacementWorkspace)

    def _place_level_loot(
        self,
        level: int,
        objs: list[PlacedObject],
        seerhut_artifacts: set[str],
        home_zids: set[int],
    ) -> tuple[list[PlacedObject], dict[Tile, float]]:
        """Seer-hut quests and guarded pocket caches for ONE level. ``objs`` is the level's
        existing objects, read only. Returns (new_objs, pocket_depth_by_tile)."""
        size, seed = self.size, self.seed
        targets = self._targets[level]
        zone_records = self._zone_records[level]
        border_guards = self._workspace.levels[level].guard_tiles
        _raw_pkt, _pocket_tiles_pkt = _precompute_pockets(zone_records)
        qobjs, n_quests = CA.place_seer_hut_quests(
            zone_records,
            seed=seed,
            bounds=(size, size),
            used_artifacts=seerhut_artifacts,
            context=CA.SeerHutContext(pocket_tiles=_pocket_tiles_pkt, existing_objs=objs),
        )
        targets.extend((o.x, o.y) for o in qobjs)
        if n_quests:
            print(f"  L{level} seer hut quests: {n_quests}")

        cobjs, n_pockets, pocket_depth_by_tile = CA.place_pocket_caches(
            zone_records,
            seed=seed,
            bounds=(size, size),
            context=CA.PocketContext(
                border_guards=border_guards,
                precomputed_pockets=_raw_pkt,
                existing_objs=[*objs, *qobjs],
                home_zids=home_zids,
            ),
        )
        targets.extend((o.x, o.y) for o in cobjs)
        ck = collections.Counter(o.purpose for o in cobjs)
        print(
            f"  L{level} pockets: {n_pockets} found, cache res={ck.get('RESOURCE_PILE', 0)} "
            + f"art={ck.get('REWARD_PICKUP', 0)} guard={ck.get('GUARD', 0)}"
        )
        return [*qobjs, *cobjs], pocket_depth_by_tile

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        objs_by_level: dict[int, list[PlacedObject]] = {lvl: [] for lvl in self._zone_records}
        for o in map_state.objs:
            if o.level in objs_by_level:
                objs_by_level[o.level].append(o)

        seerhut_artifacts: set[str] = set()
        pockets_by_level: Pockets = {}
        for level in sorted(objs_by_level):
            home_zids = {zid for lvl, zid in self._player_zids if lvl == level}
            new_objs, depth = self._place_level_loot(
                level, objs_by_level[level], seerhut_artifacts, home_zids
            )
            for o in new_objs:
                o.level = level
            self.objs.extend(new_objs)
            pockets_by_level[level] = depth

        map_state.add_objs(self.objs, TerrainGate(ontology))
        self._ctx.provide(LootResult(pockets=pockets_by_level))
