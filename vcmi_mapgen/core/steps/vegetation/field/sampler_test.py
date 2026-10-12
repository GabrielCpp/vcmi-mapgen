"""Tests for the field sampler."""

from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler
from vcmi_mapgen.core.steps.vegetation.model import VegModel, build_model
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions


def _zone(ts: set[Tile], cx: float, cy: float) -> Zone:
    return Zone(
        terrain_type=Terrain(2),
        area=len(ts),
        centroid=(cx, cy),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def test_the_field_sampler_is_deterministic_and_keeps_the_web_open(
    catalog: Catalog, priors: Priors
) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ts = {(x, y) for x in range(20) for y in range(16)}
    ref = ZoneRef(ts, label_zones({1: _zone(ts, 9.5, 7.5)}), 1, (9.5, 7.5))
    objs, blocked, prot = FieldSampler().sample(ref, model, 9, SampleOptions())
    again, blocked_again, _ = FieldSampler().sample(ref, model, 9, SampleOptions())
    assert objs == again and blocked == blocked_again
    assert objs, "some vegetation filled"
    assert blocked <= ts
    assert not (blocked & prot)


def _single_share(model: VegModel) -> float:
    sums = cast(NDArray[np.float64], model.L.sum(axis=1))
    rows = cast(list[float], sums.tolist())
    singles = 0.0
    for c, drawn in enumerate(rows):
        ws = model.iweights[c]
        one = sum(w for w, cells in zip(ws, model.iblk[c], strict=True) if len(cells) == 1)
        singles += drawn * one / sum(ws)
    return singles / sum(rows)


def test_a_thin_strip_gets_single_tile_blockers_at_the_corpus_share(
    catalog: Catalog, priors: Priors
) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ts = {(x, y) for x in range(60) for y in range(5)}
    ref = ZoneRef(ts, label_zones({1: _zone(ts, 29.5, 2.0)}), 1, (29.5, 2.0))
    placed = [
        o for seed in range(6) for o in FieldSampler().sample(ref, model, seed, SampleOptions())[0]
    ]
    spec = [catalog.spec(o.kind) for o in placed]
    singles = sum(1 for s in spec if s and sum(r.blocks for *_d, r in s.footprint.cells) == 1)
    assert singles / len(placed) <= _single_share(model)
