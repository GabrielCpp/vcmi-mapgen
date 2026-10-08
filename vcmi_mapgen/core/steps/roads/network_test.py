"""Tests for the road network."""

from dataclasses import replace

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import plan_passages
from vcmi_mapgen.core.priors.places import RoadCount, RoadStats
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.reading.roads import crossed_pairs
from vcmi_mapgen.core.steps.roads.layer import RoadLevel, RoadPlace
from vcmi_mapgen.core.steps.roads.network import RoadRules, lay_network, rules_of

W, H = 12, 6
HOME: Tile = (1, 3)
SITE: Tile = (9, 2)


def _level(kind: AdjacencyKind, walk: frozenset[Tile] | None = None) -> RoadLevel:
    label = [[0 if x < W // 2 else 1 for x in range(W)] for _ in range(H)]
    kinds = {(0, 1): kind}
    return RoadLevel(
        walk=walk if walk is not None else frozenset((x, y) for x in range(W) for y in range(H)),
        terrain=[[Terrain.GRASS] * W for _ in range(H)],
        label=label,
        places={
            0: RoadPlace(PlaceRole.HOME, Terrain.GRASS),
            1: RoadPlace(PlaceRole.MIDDLE, Terrain.GRASS),
        },
        kinds=kinds,
        passages=plan_passages(label, kinds),
        homes=((0, HOME),),
        sites={1: (SITE,)},
    )


def _rules() -> RoadRules:
    return RoadRules(share=0.5)


def test_a_home_road_crosses_a_gated_border_to_the_site_beyond() -> None:
    level = _level(AdjacencyKind.GATED)
    roads = lay_network(level, _rules())
    assert HOME in roads
    assert SITE in roads
    assert crossed_pairs(level.label, roads) == {(0, 1)}


def test_a_road_crosses_a_gated_border_only_through_its_passage() -> None:
    level = _level(AdjacencyKind.GATED)
    roads = lay_network(level, _rules())
    band = {t for es in level.passages.entrances.values() for e in es for t in e.band}
    steps = [((x, y), (x + 1, y)) for x, y in roads if x == W // 2 - 1 and (x + 1, y) in roads]
    assert steps
    assert all(u in band or v in band for u, v in steps)


def test_no_road_enters_a_place_behind_a_closed_border() -> None:
    level = _level(AdjacencyKind.CLOSED)
    roads = lay_network(level, _rules())
    assert roads
    assert all(x < W // 2 for x, _ in roads)


def test_every_road_tile_is_walkable() -> None:
    blocked = {(x, y) for x in range(3, 5) for y in range(1, 6)}
    walk = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in blocked)
    roads = lay_network(_level(AdjacencyKind.GATED, walk), _rules())
    assert SITE in roads
    assert set(roads) <= walk


def test_every_road_tile_takes_the_level_surface() -> None:
    level = replace(_level(AdjacencyKind.GATED), surface=Road.GRAVEL)
    roads = lay_network(level, _rules())
    assert {HOME, SITE} <= set(roads)
    assert set(roads.values()) == {Road.GRAVEL}


def test_the_same_seed_lays_the_same_roads() -> None:
    level = _level(AdjacencyKind.OPEN)
    assert lay_network(level, _rules()) == lay_network(level, _rules())


def test_rules_read_the_penalty_share_and_passable_rates() -> None:
    stats = RoadStats(
        counts=(
            RoadCount(10, 100, 2, 2, 0, 2, 2),
            RoadCount(30, 100, 2, 2, 2, 2, 2),
            RoadCount(20, 100, 2, 2, 1, 2, 2),
            RoadCount(0, 100, 0, 0, 0, 0, 0),
        ),
        crossed={
            "home|middle|gated": (1, 4),
            "home|middle|closed": (2, 4),
            "home|home|open": (3, 4),
        },
        surface={0: {1: 5, 3: 1}},
        on_dominant=(80, 100),
        land_dominant=(50, 100),
    )
    rules = rules_of(stats)
    assert rules.penalty == 4.0
    assert rules.share == 0.2
    assert rules.rates == {"home|middle|gated": 0.25, "home|home|open": 0.75}
    assert rules.rate == 0.5


def test_a_road_walks_around_an_object_it_does_not_serve() -> None:
    shy = frozenset((3, y) for y in range(H - 1))
    level = replace(_level(AdjacencyKind.OPEN), shy=shy)
    roads = lay_network(level, _rules())
    assert SITE in roads
    assert not set(roads) & shy


def test_a_road_crosses_an_unserved_object_when_no_other_way_exists() -> None:
    shy = frozenset((3, y) for y in range(H))
    level = replace(_level(AdjacencyKind.OPEN), shy=shy)
    roads = lay_network(level, _rules())
    assert SITE in roads
    assert set(roads) & shy
