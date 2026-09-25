"""LootStep: seer-hut quests and guarded pocket caches over the finished level."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import final, override

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.topology import find_pockets
from vcmi_mapgen.models import MapState, PlacedObject, Pockets, Tile, ZoneRecord
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, PlacementWorkspace, ProviderRegistry
from vcmi_mapgen.steps.gameplay.step import GameplayIndex
from vcmi_mapgen.steps.loot import caches as CA
from vcmi_mapgen.steps.pickup.step import PickupIndex
from vcmi_mapgen.validate import TerrainGate


@dataclass
class LootResult:
    """Pocket geometry for PocketOverlay (level -> {tile: normalized depth 0..1}). Disposable
    analysis, not a map fact, so it is not a MapState field."""

    pockets: Pockets = field(default_factory=dict)


def dedup_nearby_guards(objs: list[PlacedObject]) -> tuple[list[PlacedObject], int]:
    """Both sides of one corridor may have guarded the same gate — keep only the
    stronger of any two GUARDs within Chebyshev 2 (deterministic scan order).

    Guards rank by WHAT they gate (user-mandated placement order: loot-zone access,
    then mines, then pockets; a border crossing is guarded only as a last resort,
    after those three have already claimed theirs — see steps/AGENTS.md-adjacent
    docs on guard placement). Rank 0 (highest): a mine's own guard, or a loot-zone
    gate/monolith/portal-rescue guard — Chebyshev <=1 from a MINE footprint or a
    QUEST_GATE/TRANSPORT access object's cells; these are load-bearing (a mine must
    always be guarded, an access object needs a fight before it can be used) and
    never lose to a lower rank. Rank 1: a pocket-mouth guard (`pocket_guard`,
    tagged by steps.loot.caches.place_pocket_caches). Rank 2 (lowest): everything
    else, including a border-seal back-path guard (`seal`, tagged by
    seal_zone_borders) — dropping ITS conflict partner is fine (that partner is
    rank 0/1 and already gates something more load-bearing); dropping the seal
    guard itself just means that one crossing goes unguarded by this rule, the
    correct outcome once a higher-ranked guard has already claimed the spot.

    A higher rank always survives a conflict with a lower one. Within the SAME
    rank, two mutual rank-0 guards both survive (never drop either); any other
    same-rank conflict falls back to the stronger-monster tiebreak.

    Per-LEVEL only: two guards that happen to share (x, y) on different levels are
    not physically near each other. Returns (deduped_objs, n_dropped)."""
    drop: set[int] = set()
    guards = [(i, o) for i, o in enumerate(objs) if o.purpose == "GUARD"]
    mine_cells = [
        (mx, my)
        for o in objs
        if o.purpose == "MINE"
        for mx, my, _ in OR.mask_cells(o.mask, o.x, o.y)
    ]
    access_cells = [
        (ax, ay)
        for o in objs
        if o.purpose in ("QUEST_GATE", "TRANSPORT")
        for ax, ay, _ in OR.mask_cells(o.mask, o.x, o.y)
    ]

    def _rank(o: PlacedObject) -> int:
        if any(max(abs(o.x - mx), abs(o.y - my)) <= 1 for mx, my in mine_cells) or any(
            max(abs(o.x - ax), abs(o.y - ay)) <= 1 for ax, ay in access_cells
        ):
            return 0
        if o.pocket_guard:
            return 1
        return 2

    ranks = {ia: _rank(oa) for ia, oa in guards}
    for a in range(len(guards)):
        ia, oa = guards[a]
        if ia in drop:
            continue
        for b in range(a + 1, len(guards)):
            ib, ob = guards[b]
            if ib in drop:
                continue
            if max(abs(oa.x - ob.x), abs(oa.y - ob.y)) <= 2:
                ra, rb = ranks[ia], ranks[ib]
                if ra < rb:
                    drop.add(ib)
                elif rb < ra:
                    drop.add(ia)
                elif ra == 0:
                    continue  # both gate a mine/access object — never drop either
                else:
                    # randomMonsterLevelN sorts by N lexically (levels 1..7)
                    drop.add(ib if str(oa.type) >= str(ob.type) else ia)
    if drop:
        objs = [o for i, o in enumerate(objs) if i not in drop]
    return objs, len(drop)


def place_level_loot(
    level: int,
    size: int,
    objs: list[PlacedObject],
    targets: list[Tile],
    zone_records: list[ZoneRecord],
    seed: int,
    seerhut_artifacts: set[str],
    border_guards: frozenset[Tile],
    home_zids: set[int],
) -> tuple[list[PlacedObject], int, dict[Tile, float]]:
    """Seer-hut quests, guarded pocket caches and nearby-guard dedup for ONE level. Returns
    (objs, n_pockets, pocket_depth_by_tile)."""
    # L4a' Seer Hut quests: one fixed named artifact + a seer hut whose mission gates on it
    # (VCMI RMG convention — "add seer hut with quest to the map like the vcmi generator
    # does"). Runs before pocket caches so its two footprints are already claimed in
    # `zone_records` when pocket geometry is judged.
    # Pre-compute global pocket geometry ONCE, shared by both the seer-hut quest pass
    # (artifact restricted to ≥3-tile pockets) and the pocket-cache pass (avoids a
    # second expensive find_pockets call on the same data).
    _global_true_pkt: set[Tile] = set()
    for _zr_pkt in zone_records:
        _global_true_pkt |= _zr_pkt.passable
    _raw_pkt = find_pockets(_global_true_pkt)
    _pocket_tiles_pkt: set[Tile] = set()
    for _g_pkt, (_pt_pkt, _mf_pkt) in _raw_pkt.items():
        if len(_pt_pkt) >= 3:
            _pocket_tiles_pkt |= set(_pt_pkt)
    qobjs, n_quests = CA.place_seer_hut_quests(
        zone_records,
        seed=seed,
        bounds=(size, size),
        used_artifacts=seerhut_artifacts,
        pocket_tiles=_pocket_tiles_pkt,
        existing_objs=objs,
    )
    objs.extend(qobjs)
    targets.extend((o.x, o.y) for o in qobjs)
    if n_quests:
        print(f"  L{level} seer hut quests: {n_quests}")

    # L4b guarded pocket caches: ONE global, zone-independent pass over this level's whole
    # reachable field now that every zone's terrain/vegetation/scatter AND the map-level
    # repair passes above are finalized (user-mandated 2026-07-04 — see
    # steps.loot.caches.place_pocket_caches docstring for the rationale).
    cobjs, n_pockets, pocket_depth_by_tile = CA.place_pocket_caches(
        zone_records,
        seed=seed,
        bounds=(size, size),
        border_guards=border_guards,
        precomputed_pockets=_raw_pkt,
        existing_objs=objs,
        home_zids=home_zids,
    )
    objs.extend(cobjs)
    targets.extend((o.x, o.y) for o in cobjs)
    ck = collections.Counter(o.purpose for o in cobjs)
    print(
        f"  L{level} pockets: {n_pockets} found, cache res={ck.get('RESOURCE_PILE', 0)} "
        + f"art={ck.get('REWARD_PICKUP', 0)} guard={ck.get('GUARD', 0)}"
    )

    objs, _ndrop = dedup_nearby_guards(objs)
    return objs, n_pockets, pocket_depth_by_tile


@final
class LootStep(PipelineStep):
    """Content that depends on the finished walkable field: seer-hut quests and guarded
    pocket caches.

    Config:
        seed        RNG seed.
        size        Map side length in tiles (square).

    inject(ctx): ``PickupIndex`` (targets/zone_records), ``GameplayIndex`` (player_zids),
    the shared ``PlacementWorkspace`` (``guard_tiles`` per level).

    Produces: replaces ``map_state.objs`` and provides ``LootResult``.
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
        pickup = ctx.require(PickupIndex)
        self._targets = pickup.targets
        self._zone_records = pickup.zone_records
        self._player_zids = ctx.require(GameplayIndex).player_zids
        self._workspace = ctx.require(PlacementWorkspace)

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
            objs, _n, depth = place_level_loot(
                level,
                self.size,
                objs_by_level[level],
                self._targets[level],
                self._zone_records[level],
                self.seed,
                seerhut_artifacts,
                self._workspace.levels[level].guard_tiles,
                home_zids,
            )
            if level == 1:
                for o in objs:
                    o.level = 1
            objs_by_level[level] = objs
            pockets_by_level[level] = depth

        self.objs = [o for lvl in sorted(objs_by_level) for o in objs_by_level[lvl]]
        map_state.set_objs(self.objs, TerrainGate(ontology))
        self._ctx.provide(LootResult(pockets=pockets_by_level))
