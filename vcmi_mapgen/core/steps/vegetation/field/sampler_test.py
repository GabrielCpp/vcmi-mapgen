"""Tests for the field sampler."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler
from vcmi_mapgen.core.steps.vegetation.model import build_model
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
