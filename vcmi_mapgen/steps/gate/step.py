"""GateStep — place Subterranean Gate pairs between surface and underground.

Only added to the pipeline when ``subterrain`` is requested; there is no internal no-op
branch here since the only caller already gates that."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import override

from vcmi_mapgen.kit.geometry import NB8
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.models import MapState, PlacedObject, Tile, Zone
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.steps.gate import gates as PG


@dataclass
class GateResult:
    """Gate objects/occupancy/approach cells — GameplayStep's/PickupStep's/RepairStep's
    input. Read via ``ctx.get(GateResult, GateResult())`` (never ``require``): a map
    without --subterrain has no GateStep, so its consumers must see the empty default,
    not an error."""

    gate_objs: list[PlacedObject] = field(default_factory=list)
    gate_occ: dict[int, set[Tile]] = field(default_factory=dict)
    gate_appr: dict[int, list[Tile]] = field(default_factory=dict)


MIN_AREA = 25  # matches GameplayStep's own zone floor — a gate must land on a tile a
#                zone's own gameplay pass would actually consider (pipeline-refactor-v2-
#                folders.md Phase 2 found this filter missing here: pre-existing, not a
#                Phase 2 regression, but required for GameplayStep's gate-object parity).


def _land_tiles(zones: Mapping[int, Zone]) -> set[Tile]:
    ts: set[Tile] = set()
    for z in zones.values():
        terrain = TNAME.get(z.terrain_type)
        if terrain in (None, "water", "rock") or z.area < MIN_AREA:
            continue
        ts.update(z.tiles_set)
    return ts


def _rim8(zones: Mapping[int, Zone]) -> frozenset[Tile]:
    """All tiles that have an 8-neighbour in a different zone (the inter-zone rim)."""
    label: dict[Tile, int] = {}
    for zid, z in zones.items():
        for t in z.tiles_set:
            label[t] = zid
    rim: set[Tile] = set()
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
        self.seed: int = seed
        self.gate_objs: list[PlacedObject] = []
        self.gate_occ: dict[int, set[Tile]] = {}
        self.gate_blk: dict[int, set[Tile]] = {}
        self.gate_appr: dict[int, list[Tile]] = {}
        self._ctx: ProviderRegistry | None = None

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._ctx = ctx

    @override
    def run(self, ontology: Ontology, map_state: MapState) -> None:
        zones0 = map_state.zones[0]
        zones1 = map_state.zones[1]
        ts0 = _land_tiles(zones0)
        ts1 = _land_tiles(zones1)

        (gobjs0, gate_occ0, gate_blk0, gate_appr0), (gobjs1, gate_occ1, gate_blk1, gate_appr1) = (
            PG.place_gates(
                ts0,
                ts1,
                set(),
                set(),
                appr0=_rim8(zones0),
                appr1=_rim8(zones1),
                seed=self.seed,
            )
        )
        print(f"  gates: {len(gobjs0)} Subterranean Gate pair(s) placed")

        self.gate_objs = gobjs0 + gobjs1
        self.gate_occ = {0: gate_occ0, 1: gate_occ1}
        self.gate_blk = {0: gate_blk0, 1: gate_blk1}
        self.gate_appr = {0: gate_appr0, 1: gate_appr1}

        map_state.gate_blk = {lvl: frozenset(blk) for lvl, blk in self.gate_blk.items()}
        if self._ctx is not None:
            self._ctx.provide(
                GateResult(
                    gate_objs=self.gate_objs, gate_occ=self.gate_occ, gate_appr=self.gate_appr
                )
            )
