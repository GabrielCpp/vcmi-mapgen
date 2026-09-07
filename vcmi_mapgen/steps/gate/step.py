"""GateStep — place Subterranean Gate pairs between surface and underground.

Only added to the pipeline when ``subterrain`` is requested; there is no internal no-op
branch here since the only caller already gates that."""
from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.steps.gate import gates as PG


@dataclass
class GateResult:
    """Gate objects/occupancy/approach cells — GameplayStep's/PickupStep's/RepairStep's
    input. Read via ``ctx.get(GateResult, GateResult())`` (never ``require``): a map
    without --subterrain has no GateStep, so its consumers must see the empty default,
    not an error."""

    gate_objs: list = field(default_factory=list)
    gate_occ: dict = field(default_factory=dict)
    gate_appr: dict = field(default_factory=dict)

MIN_AREA = 25  # matches GameplayStep's own zone floor — a gate must land on a tile a
#                zone's own gameplay pass would actually consider (pipeline-refactor-v2-
#                folders.md Phase 2 found this filter missing here: pre-existing, not a
#                Phase 2 regression, but required for GameplayStep's gate-object parity).


def _land_tiles(zones):
    ts = set()
    for z in zones.values():
        terrain = TNAME.get(z["terrain_type"])
        if terrain in (None, "water", "rock") or z["area"] < MIN_AREA:
            continue
        ts.update(z["tiles_set"])
    return ts


def _rim8(zones):
    """All tiles that have an 8-neighbour in a different zone (the inter-zone rim)."""
    NB8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    label = {}
    for zid, z in zones.items():
        for t in z["tiles_set"]:
            label[t] = zid
    rim = set()
    for (x, y), zid in label.items():
        for dx, dy in NB8:
            nb = (x + dx, y + dy)
            if label.get(nb, zid) != zid:
                rim.add((x, y))
                break
    return frozenset(rim)


class GateStep(PipelineStep):
    """Place Subterranean Gate pairs.

    Config:
        seed  RNG seed (should match the seed used for terrain generation).

    Reads ``map_state.zones`` (SegmentStep's output) directly in run().

    Produces:
      - ``gate_blk``    — blocked tile sets per level, written directly onto MapState.
      - ``GateResult``  — gate_objs/gate_occ/gate_appr, published into ctx (GameplayStep's/
        PickupStep's/RepairStep's input; each defaults to empty when no GateStep ran).
    """

    def __init__(self, seed: int = 3) -> None:
        self.seed = seed
        self.gate_objs: list = []
        self.gate_occ: dict = {}
        self.gate_blk: dict = {}
        self.gate_appr: dict = {}
        self._ctx = None

    def inject(self, ctx) -> None:
        self._ctx = ctx

    def run(self, ontology, map_state) -> None:
        zones0 = map_state.zones[0]
        zones1 = map_state.zones[1]
        ts0 = _land_tiles(zones0)
        ts1 = _land_tiles(zones1)

        (gobjs0, gate_occ0, gate_blk0, gate_appr0), \
        (gobjs1, gate_occ1, gate_blk1, gate_appr1) = PG.place_gates(
            ts0, ts1, set(), set(),
            appr0=_rim8(zones0), appr1=_rim8(zones1),
            seed=self.seed,
        )
        print(f"  gates: {len(gobjs0)} Subterranean Gate pair(s) placed")

        self.gate_objs = gobjs0 + gobjs1
        self.gate_occ = {0: gate_occ0, 1: gate_occ1}
        self.gate_blk = {0: gate_blk0, 1: gate_blk1}
        self.gate_appr = {0: gate_appr0, 1: gate_appr1}

        map_state.gate_blk = self.gate_blk
        self._ctx.provide(GateResult(gate_objs=self.gate_objs, gate_occ=self.gate_occ,
                                     gate_appr=self.gate_appr))
