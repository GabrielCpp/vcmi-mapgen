"""PickupStep — the global loot-zone access pass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import override

from vcmi_mapgen.models import MapState, PlacedObject, Tile, ZoneRecord
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import (
    LevelWorkspace,
    PipelineStep,
    PlacementWorkspace,
    ProviderRegistry,
)
from vcmi_mapgen.steps.gate.step import GateResult
from vcmi_mapgen.steps.pickup import loot_zones as LZ
from vcmi_mapgen.steps.pickup import scatter as SC
from vcmi_mapgen.validate import TerrainGate


@dataclass
class PickupIndex:
    """Per-level repair targets + zone records — BorderStep's input (and mutated
    further in place by it: this is the same object PickupStep computed, not a fresh
    snapshot each demand)."""

    targets: dict[int, list[Tile]] = field(default_factory=dict)
    zone_records: dict[int, list[ZoneRecord]] = field(default_factory=dict)


class PickupStep(PipelineStep):
    """The global, per-level loot-zone access pass (gate+keymaster / sealed+monolith).

    Config:
        seed       RNG seed.
        size       Map side length in tiles (square).

    Reads ``map_state.objs`` (Gameplay's + Vegetation's, already merged) and
    ``map_state.zones`` (SegmentStep's output) directly in run(). inject(ctx): the
    folded-in ``PlacementWorkspace`` (reads each zone's ``blocked``/``open_set``/
    ``passable`` written by VegetationStep plus the gameplay fields GameplayStep wrote,
    and writes ``reach``/``used`` back per zone and ``hard_avoid`` per
    level for BorderStep), ``GateResult`` (GateStep's output, defaults to empty when
    there is no GateStep).

    Produces: replaces ``map_state.objs`` (the full, repartitioned
    loot-zone list, underground tagged ``l=1`` — this REPLACES the prior value, it
    doesn't just append to it). Into ctx: ``PickupIndex`` (targets/zone_records, the
    list-of-dicts shape BorderStep expects).
    """

    def __init__(self, seed: int = 3, size: int = 72) -> None:
        self.seed: int = seed
        self.size: int = size
        self.objs: list[PlacedObject] = []
        self.targets: dict[int, list[Tile]] = {}
        self.zone_records: dict[int, list[ZoneRecord]] = {}
        self._ctx: ProviderRegistry | None = None
        self._workspace: PlacementWorkspace | None = None
        self._gate_objs: list[PlacedObject] = []

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx
        self._workspace = ctx.require(PlacementWorkspace)
        self._gate_objs = ctx.get(GateResult, GateResult()).gate_objs

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        assert self._workspace is not None
        assert self._ctx is not None

        # partition the flat objs list by level — place_loot_zones mutates its
        # objs_existing list in place (clearing vegetation/scatter under a sealed
        # loot zone), so each level needs its own real (not concatenated-copy) list.
        objs_by_level: dict[int, list[PlacedObject]] = {
            level: [] for level in self._workspace.levels
        }
        for o in map_state.objs:
            lvl = o.level
            if lvl in objs_by_level:
                objs_by_level[lvl].append(o)

        for level, lvl_ws in self._workspace.levels.items():
            self._run_level(level, lvl_ws, objs_by_level[level])

        self.objs = [o for lvl in sorted(objs_by_level) for o in objs_by_level[lvl]]
        map_state.set_objs(self.objs, TerrainGate(ontology))
        self._ctx.provide(PickupIndex(targets=self.targets, zone_records=self.zone_records))

    @staticmethod
    def _zone_records(lvl_ws: LevelWorkspace, targets: list[Tile]) -> list[ZoneRecord]:
        zone_records: list[ZoneRecord] = []
        for zid, zw in sorted(lvl_ws.zones.items()):
            reach = SC.scatter_reach(zw.open_set - (zw.rim8 - zw.ent_bands), zw.prot)

            targets.extend(zw.approaches)
            # every planned crossing must survive repair: its rep is a named G2
            # target, so the reachability check verifies the entrance stayed connected once the
            # level is finalized
            targets.extend(r for r, _b, _o in zw.entrances)
            # Seaport approach tile must stay reachable (hero boards ship from there)
            targets.extend(t for t in (lvl_ws.seaport_appr & zw.ts_full))

            # BorderStep mutates open_set/passable in place (.add/.discard) — these
            # must be plain sets, not the workspace's frozensets.
            zone_records.append(
                ZoneRecord(
                    zid=zid,
                    terrain=zw.terrain,
                    ts=zw.ts_full,
                    open_set=set(zw.open_set),
                    passable=set(zw.passable),
                    reach=reach,
                    used=set(),
                )
            )
        return zone_records

    def _run_level(
        self, level: int, lvl_ws: LevelWorkspace, level_objs: list[PlacedObject]
    ) -> None:
        W = H = self.size
        targets: list[Tile] = []
        hard_avoid: set[Tile] = set()
        zone_records = self._zone_records(lvl_ws, targets)

        # place_loot_zones clears every object under a newly-sealed loot zone by
        # (x, y) alone (see loot_zones.py), which would sweep a pre-placed
        # Subterranean Gate (+ its approach guard) if one falls inside the zone's
        # tile set — a Gate pair shares its (x, y) with its OTHER-level counterpart.
        # Legacy build() only appended gate_objs to `objs` AFTER this pass ran, so
        # they were physically absent here and immune; this pipeline merges them in
        # earlier (GameplayStep, so downstream forbid/occupied sets see them), so we
        # must shield them from the sweep by pulling them out and restoring them.
        gate_ids = {id(o) for o in self._gate_objs if o.level == level}
        shielded = [o for o in level_objs if id(o) in gate_ids]
        level_objs[:] = [o for o in level_objs if id(o) not in gate_ids]

        loot_objs, n_loot, loot_zids = LZ.place_loot_zones(
            zone_records, level_objs, seed=self.seed, bounds=(W, H), fixed=shielded
        )
        if level == 1:  # place_loot_zones always tags l=0; retag the underground level
            for o in loot_objs:
                o.level = 1
        level_objs.extend(shielded)
        level_objs.extend(loot_objs)
        # Only add EXTERIOR loot zone objects to targets (keymaster, exterior monolith).
        # Interior objects (gate, interior monolith) are reachable via teleportation/
        # gate, not via physical traversal. Counting them would fail the portal reachability
        # check, since no walking path reaches them.
        loot_interior_tiles: set[Tile] = set()
        for zr in zone_records:
            if zr.zid in loot_zids:
                loot_interior_tiles |= zr.ts
        targets.extend(
            (o.x, o.y) for o in loot_objs if o.purpose and (o.x, o.y) not in loot_interior_tiles
        )
        targets[:] = [t for t in targets if t not in loot_interior_tiles]
        # Mark sealed loot zones so place_pocket_caches excludes them from its
        # detection universe — their interiors would otherwise appear as pockets and
        # receive a spurious interior guard (the access mechanic already provides the
        # gate keeper).
        for zr in zone_records:
            if zr.zid in loot_zids:
                zr.loot_zone = True
        _report_loot(level, n_loot, loot_zids)

        for zr in zone_records:
            zw = lvl_ws.zones[zr.zid]
            hard_avoid |= set(zw.occupied) | set(zw.approaches)

        lvl_ws.hard_avoid = hard_avoid
        self.targets[level] = targets
        self.zone_records[level] = zone_records


def _report_loot(level: int, n_loot: int, loot_zids: set[int]) -> None:
    if n_loot:
        zid_str = ", ".join(str(z) for z in sorted(loot_zids))
        print(
            f"  L{level} loot zones: {n_loot} access pair(s) placed "
            + f"(1 gate+key, {n_loot - 1} sealed+monolith) zones=[{zid_str}]"
            if n_loot > 1
            else f"  L{level} loot zones: 1 gate+key pair placed zones=[{zid_str}]"
        )
