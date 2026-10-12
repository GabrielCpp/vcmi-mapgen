from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.vegetation.canvas import ZoneCanvas
from vcmi_mapgen.core.steps.vegetation.model import build_model
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions


def _zone(ts: set[Tile]) -> Zone:
    return Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(0.0, 0.0),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def test_the_canvas_never_walls_off_the_next_zones_land(catalog: Catalog, priors: Priors) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ts = {(x, y) for x in range(6) for y in range(6)}
    tip = (6, 2)
    ref = ZoneRef(ts, label_zones({1: _zone(ts), 2: _zone({tip})}), 1, (2.5, 2.5))
    alone = ZoneCanvas(ref, model, SampleOptions(prot={(0, 0)}))
    beside = ZoneCanvas(ref, model, SampleOptions(prot={(0, 0)}, land=frozenset({tip})))
    assert alone.try_place((5, 2, 0, 0), [(5, 2)])
    assert not beside.try_place((5, 2, 0, 0), [(5, 2)])


def test_the_canvas_never_walls_off_a_cove_from_its_own_zone(
    catalog: Catalog, priors: Priors
) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    body = {(x, y) for x in range(6) for y in range(3, 6)}
    cove = {(0, 0), (0, 1), (0, 2)}
    ts = body | cove
    side = {(1, 0), (1, 1)}
    ref = ZoneRef(ts, label_zones({1: _zone(ts), 2: _zone(side)}), 1, (2.5, 4.0))
    canvas = ZoneCanvas(ref, model, SampleOptions(prot={(3, 4), (1, 0)}, land=frozenset(ts | side)))
    assert not canvas.try_place((0, 2, 0, 0), [(0, 2)])
    assert canvas.try_place((5, 5, 0, 0), [(5, 5)])
