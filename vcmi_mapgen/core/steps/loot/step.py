"""LootStep: seer-hut quests and guarded pocket caches over the finished level."""

from __future__ import annotations

import collections
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from typing import final, override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.pockets import Pockets, find_pockets, find_rooms
from vcmi_mapgen.core.model import CoverIndex, MapState, PlacedObject, PlacementRule, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.placement.start_room import start_rules
from vcmi_mapgen.core.planning.content import ContentPlan
from vcmi_mapgen.core.planning.guarding import prize_guard
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.pocket_masks import PocketMask
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.loot import pickups as PK
from vcmi_mapgen.core.steps.loot import pocket_plan as PP
from vcmi_mapgen.core.steps.loot import quests as QU
from vcmi_mapgen.core.steps.loot.pockets import access_tiles, occupied_tiles
from vcmi_mapgen.core.steps.loot.result import LootResult


def _precompute_pockets(
    zone_records: list[ZoneRecord],
    masks: Sequence[PocketMask],
    access: AbstractSet[Tile],
    occupied: AbstractSet[Tile],
) -> tuple[dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]], set[Tile]]:
    _global_true_pkt: set[Tile] = set()
    for _zr_pkt in zone_records:
        _global_true_pkt |= _zr_pkt.passable
    _raw_pkt = find_pockets(_global_true_pkt, masks, access, occupied)
    _pocket_tiles_pkt: set[Tile] = set()
    for _g_pkt, (_pt_pkt, _mf_pkt) in _raw_pkt.items():
        if len(_pt_pkt) >= 3:
            _pocket_tiles_pkt |= set(_pt_pkt)
    return _raw_pkt, _pocket_tiles_pkt


def _with_rooms(
    raw: dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]],
    zone_records: Sequence[ZoneRecord],
    barred: AbstractSet[Tile],
) -> dict[Tile, tuple[frozenset[Tile], frozenset[Tile]]]:
    passable = frozenset(t for zr in zone_records for t in zr.passable)
    loot = {t for zr in zone_records if zr.loot_zone for t in zr.ts}
    merged = dict(raw)
    for g, room in find_rooms(passable, barred | loot).items():
        if g not in merged or len(room[0]) > len(merged[g][0]):
            merged[g] = room
    return merged


@final
class LootStep(PipelineStep):
    """Content that depends on the finished walkable field: seer-hut quests and guarded
    pocket caches.

    Config:
        priors      The corpus priors; the step reads the level-0 gameplay statistics and
                    each level's place content.
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``ZoneIndex`` (targets/zone_records), ``TownsIndex`` (player_zids) and
    ``ContentPlan``, whose intents turn on the planned pockets of a level and whose hops
    pick each pocket guard's level from the corpus spread.

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
        self._plan = ContentPlan()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        zones = ctx.require(ZoneIndex)
        self._targets = zones.targets
        self._zone_records = zones.zone_records
        self._claims = zones.claims
        self._player_zids = ctx.require(TownsIndex).player_zids
        self._plan = ctx.get(ContentPlan, ContentPlan())

    def _place_level_loot(
        self,
        catalog: Catalog,
        level: int,
        objs: list[PlacedObject],
        seerhut_artifacts: set[str],
        rules: Sequence[PlacementRule],
    ) -> PK.PocketFill:
        """Seer-hut quests and guarded pocket caches for ONE level. ``objs`` is the level's
        existing objects, read only. Returns the new objects, the pocket depths and the
        prize slots the pockets hold open."""
        size, seed = self.size, self.seed
        home_zids = {zid for lvl, zid in self._player_zids if lvl == level}
        targets = self._targets[level]
        zone_records = self._zone_records[level]
        access, occupied = access_tiles(objs), occupied_tiles(objs)
        _raw_pkt, _pocket_tiles_pkt = _precompute_pockets(
            zone_records, self.priors.pocket_masks, access, occupied
        )
        intents = {z: i for (lvl, z), i in self._plan.intents.items() if lvl == level}
        plan = PP.level_plan(intents, zone_records)
        if plan is not None:
            _raw_pkt = _with_rooms(_raw_pkt, zone_records, access | occupied)
        cover = CoverIndex(objs, self._claims.get(level, ()), rules)
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

        fill = PK.place_pocket_caches(
            catalog,
            zone_records,
            seed=seed,
            bounds=(size, size),
            context=PK.PocketContext(
                self.priors.gameplay[0],
                pockets=_raw_pkt,
                existing_objs=[*objs, *qobjs],
                home_zids=home_zids,
                cover=cover,
                plan=plan,
                guard=prize_guard(self.priors.places, self._plan, level),
                level=level,
            ),
        )
        cobjs = fill.objs
        targets.extend((o.x, o.y) for o in cobjs)
        targets.extend(h.tile for h in fill.held)
        self._claims[level] = frozenset(cover.claims)
        ck = collections.Counter(o.purpose for o in cobjs)
        res, art = ck.get(Purpose.RESOURCE_PILE, 0), ck.get(Purpose.REWARD_PICKUP, 0)
        print(
            f"  L{level} pockets: {fill.n_pockets} found, cache res={res} "
            + f"art={art} held={len(fill.held)} guard={ck.get(Purpose.GUARD, 0)}"
        )
        return PK.PocketFill([*qobjs, *cobjs], fill.n_pockets, fill.depth, fill.held)

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        objs_by_level = map_state.objs_by_level(self._zone_records)

        seerhut_artifacts = QU.set_artifacts(catalog)
        pockets_by_level: Pockets = {}
        held: list[HeldPrize] = []
        for level in sorted(objs_by_level):
            fill = self._place_level_loot(
                catalog,
                level,
                objs_by_level[level],
                seerhut_artifacts,
                start_rules(map_state, level),
            )
            for o in fill.objs:
                o.level = level
            self.objs.extend(fill.objs)
            pockets_by_level[level] = fill.depth
            held.extend(fill.held)

        map_state.add_objs(self.objs)
        self._ctx.provide(LootResult(pockets=pockets_by_level, held=tuple(held)))
