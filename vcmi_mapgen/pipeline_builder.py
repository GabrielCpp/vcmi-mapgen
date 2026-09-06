"""PipelineBuilder — hand-wired construction of both pipeline families.

No DI framework, no shared mutable state object threaded through steps: each subcommand
gets its own straight-line method here that constructs a step, runs it, reads back
whichever of its properties a later step needs, and calls that step's ``inject()``.

The ``generate`` family (``run_generate``) is the only CLI-configurable one — it accepts
a ``stop_after`` prefix cut of its otherwise-fixed step sequence. The identity-rebuild
family (``run_identity_rebuild`` / ``run_deform_rebuild``) is fixed: cli.py's subcommands
each call exactly one of these with no further configurability.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.pipeline import MapState, PlacementWorkspace
from vcmi_mapgen.steps import (
    DeformWarpStep, ExtractTemplateStep, FmDocumentStep, GameplayStep, GateStep,
    PickupStep, RebuildMapStep, RepairStep, SegmentStep, TerrainGenStep, TileStep,
    VegetationStep, VerifyStep,
)

GENERATE_STOP_POINTS = (
    "terrain_gen", "tile", "segment", "gate", "gameplay", "vegetation", "pickup",
)


@dataclass
class GenerateResult:
    state: MapState
    log: list = field(default_factory=list)
    player_zids: list = field(default_factory=list)


@dataclass
class IdentityRebuildResult:
    template: dict
    fm: dict
    stats: dict
    document: object
    verify: tuple | None = None   # (ok, total, matched, missing, extra), or None if unverified


class PipelineBuilder:
    def run_generate(self, *, seed: int, size: int, water_mode: str = "normal",
                      subterrain: bool = False, players: int = 0,
                      stop_after: str | None = None) -> GenerateResult:
        if stop_after is not None and stop_after not in GENERATE_STOP_POINTS:
            raise ValueError(
                f"stop_after must be one of {GENERATE_STOP_POINTS} or None, got {stop_after!r}")

        workspace = PlacementWorkspace()
        state = MapState(size=size)
        player_zids: list = []
        log: list = []

        terrain = TerrainGenStep(size=size, seed=seed, water_mode=water_mode,
                                 subterrain=subterrain)
        terrain.run()
        if stop_after == "terrain_gen":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        tile = TileStep(size=size)
        tile.inject(grids=terrain.grids, tunnel_protect=terrain.tunnel_protect)
        tile.run()
        state.surfs, state.cells = tile.surfs, tile.cells
        if stop_after == "tile":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        segment = SegmentStep()
        segment.inject(cells=tile.cells, tunnel_protect=terrain.tunnel_protect)
        segment.run()
        state.zones = segment.zones
        if stop_after == "segment":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        gate = None
        if subterrain:
            gate = GateStep(seed=seed)
            gate.inject(zones=segment.zones)
            gate.run()
            state.gate_blk = gate.gate_blk
        if stop_after == "gate":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        gameplay = GameplayStep(seed=seed, players=players, size=size,
                                subterrain=subterrain, workspace=workspace)
        gameplay.inject(
            grids=tile.grids, zones=segment.zones, tunnel_protect=terrain.tunnel_protect,
            gate_objs=gate.gate_objs if gate else (),
            gate_occ=gate.gate_occ if gate else {},
            gate_blk=gate.gate_blk if gate else {},
            gate_appr=gate.gate_appr if gate else {},
        )
        gameplay.run()
        state.objs = gameplay.objs
        state.player_towns = gameplay.player_towns
        player_zids = gameplay.player_zids
        if stop_after == "gameplay":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        vegetation = VegetationStep(seed=seed, workspace=workspace)
        vegetation.inject(zones=segment.zones)
        vegetation.run()
        state.objs = gameplay.objs + vegetation.objs
        if stop_after == "vegetation":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        pickup = PickupStep(seed=seed, size=size, workspace=workspace)
        pickup.inject(objs=state.objs, zones=segment.zones,
                      gate_objs=gate.gate_objs if gate else ())
        pickup.run()
        state.objs = pickup.objs
        if stop_after == "pickup":
            return GenerateResult(state=state, log=log, player_zids=player_zids)

        repair = RepairStep(seed=seed, size=size, subterrain=subterrain, workspace=workspace)
        repair.inject(
            objs=pickup.objs, targets=pickup.targets, zone_records=pickup.zone_records,
            grids=tile.grids, zones=segment.zones, player_zids=gameplay.player_zids,
            gate_objs=gate.gate_objs if gate else (), tunnel_protect=terrain.tunnel_protect,
        )
        repair.run()
        state.objs = repair.objs
        log = repair.log

        return GenerateResult(state=state, log=log, player_zids=player_zids)

    def run_identity_rebuild(self, name: str, out_name: str,
                             verify: bool = False) -> IdentityRebuildResult:
        extract = ExtractTemplateStep(name)
        extract.run()

        src = OR.load_faithful(name)
        rebuild = RebuildMapStep(identity=True)
        rebuild.inject(template=extract.template, target_terrain=src["terrain"])
        rebuild.run()

        verify_result = None
        if verify:
            vstep = VerifyStep(name)
            vstep.inject(fm=rebuild.fm)
            vstep.run()
            verify_result = (vstep.ok, vstep.total, vstep.matched, vstep.missing, vstep.extra)

        doc = FmDocumentStep(out_name)
        doc.inject(fm=rebuild.fm)
        doc.run()

        return IdentityRebuildResult(template=extract.template, fm=rebuild.fm,
                                     stats=rebuild.stats, document=doc.document,
                                     verify=verify_result)

    def run_deform_rebuild(self, name: str, zone_id: int,
                           out_name: str) -> IdentityRebuildResult:
        extract = ExtractTemplateStep(name)
        extract.run()

        deform = DeformWarpStep(name, zone_id)
        deform.inject(template=extract.template)
        deform.run()

        doc = FmDocumentStep(out_name)
        doc.inject(fm=deform.fm)
        doc.run()

        return IdentityRebuildResult(template=extract.template, fm=deform.fm, stats={},
                                     document=doc.document, verify=None)
