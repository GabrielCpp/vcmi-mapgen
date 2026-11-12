"""SeaStep: rocks, reefs and kelp on the water at the corpus rate."""

from __future__ import annotations

import random
from typing import override

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import PipelineStep, ProviderRegistry
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.sea.dress import SeaLevel, dress_level

MIN_WATER = 0.02


class SeaStep(PipelineStep):
    """Water decoration after every gameplay object. The map draws one corpus map's share
    of blocked water, and each decoration's kind at the corpus kind odds. A decoration
    never blocks a tile beside a cell a hero steps on, and never splits a sea.

    Config:
        priors     The corpus priors; the step reads the water targets and kind counts.
        seed       RNG seed.

    inject(ctx): ``ZoneIndex`` when present, for the claimed tiles.

    Produces: appends the decorations to ``map_state.objs``.
    """

    def __init__(self, priors: Priors, seed: int = 3) -> None:
        self.priors: Priors = priors
        self.seed: int = seed
        self._zones: ZoneIndex = ZoneIndex()

    @override
    def inject(self, ctx: ProviderRegistry) -> None:
        self._zones = ctx.get(ZoneIndex, ZoneIndex())

    @override
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        rng = random.Random(f"{self.seed}:sea")
        rates = [t.dress for t in self.priors.water.targets if t.share >= MIN_WATER]
        rate = rng.choice(rates) if rates else 0.0
        kinds = water_kinds(catalog.water_decor(), dict(self.priors.water.dress_kinds))
        by_level = map_state.objs_by_level(map_state.terrain)
        for level, grid in map_state.terrain.items():
            objs = by_level[level]
            lv = SeaLevel(
                level,
                frozenset(_water(grid)),
                map_state.taken_tiles(level) | self._zones.claims.get(level, frozenset()),
                frozenset(FP.blocking_cells(objs)) | map_state.gate_blk.get(level, frozenset()),
                frozenset(t for o in objs for t in FP.interactive_cells(o.footprint, o.x, o.y)),
                rate,
            )
            map_state.add_objs(dress_level(lv, kinds, rng))


def water_kinds(pool: list[Identity], counts: dict[str, int]) -> list[tuple[Identity, float]]:
    """Each water decoration of ``pool`` the corpus holds, weighted by its corpus count."""
    return [(i, float(counts[i.kind.lower()])) for i in pool if counts.get(i.kind.lower(), 0) > 0]


def _water(grid: list[list[Terrain]]) -> list[Tile]:
    return [(x, y) for y, row in enumerate(grid) for x, t in enumerate(row) if t == Terrain.WATER]
