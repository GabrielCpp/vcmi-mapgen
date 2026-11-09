"""The routes sampler on one open zone: it is deterministic, keeps the web open, blocks
about the corpus share, and leaves ground a hero crosses straighter than the cellular
field's."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.reach import STEPS8, distances
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.winding import route_winding
from vcmi_mapgen.core.steps.vegetation.field.sampler import FieldSampler
from vcmi_mapgen.core.steps.vegetation.model import build_model
from vcmi_mapgen.core.steps.vegetation.routes.net import STRETCH
from vcmi_mapgen.core.steps.vegetation.routes.sampler import RoutesSampler
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, Sampler

W, H = 44, 36


def _ref() -> ZoneRef:
    ts = {(x, y) for x in range(W) for y in range(H)}
    zone = Zone(
        terrain_type=Terrain(2),
        area=len(ts),
        centroid=(W / 2, H / 2),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )
    return ZoneRef(ts, label_zones({1: zone}), 1, (W / 2, H / 2))


def _winding(sampler: Sampler, catalog: Catalog, priors: Priors) -> list[float]:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ref = _ref()
    out: list[float] = []
    for seed in range(4):
        _, blocked, _ = sampler.sample(ref, model, seed, SampleOptions())
        w = route_winding(set(ref.ts) - blocked, max(W, H))
        assert w is not None
        out.append(w)
    return out


def test_the_routes_sampler_is_deterministic_and_keeps_the_web_open(
    catalog: Catalog, priors: Priors
) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ref = _ref()
    objs, blocked, prot = RoutesSampler().sample(ref, model, 9, SampleOptions())
    again, blocked_again, _ = RoutesSampler().sample(ref, model, 9, SampleOptions())
    assert objs == again and blocked == blocked_again
    assert blocked <= ref.ts
    assert not (blocked & prot)


def test_the_routes_sampler_blocks_about_the_field_share(catalog: Catalog, priors: Priors) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ref = _ref()
    routes = sum(len(RoutesSampler().sample(ref, model, s, SampleOptions())[1]) for s in range(4))
    field = sum(len(FieldSampler().sample(ref, model, s, SampleOptions())[1]) for s in range(4))
    assert abs(routes - field) <= 0.1 * field


def test_ground_left_by_routes_winds_less_than_the_cellular_field(
    catalog: Catalog, priors: Priors
) -> None:
    routes = _winding(RoutesSampler(), catalog, priors)
    field = _winding(FieldSampler(), catalog, priors)
    assert sum(routes) < sum(field)
    assert max(routes) < 1.3


def test_a_hero_walks_between_two_ways_in_close_to_the_straight_line(
    catalog: Catalog, priors: Priors
) -> None:
    model = build_model(catalog, "grass", priors.vegetation["grass"])
    ref = _ref()
    west = frozenset((0, y) for y in range(7, 10))
    east = frozenset((W - 1, y) for y in range(26, 29))
    for seed in range(4):
        _, blocked, _ = RoutesSampler().sample(ref, model, seed, SampleOptions(prot=west | east))
        steps = distances(set(ref.ts) - blocked, [(0, 8)], STEPS8)
        assert steps[(W - 1, 27)] <= STRETCH * (W - 1)
