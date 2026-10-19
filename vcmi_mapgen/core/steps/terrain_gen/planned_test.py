"""The planned front seats every player in its own territory and keeps each place inside
one territory."""

from collections.abc import Sequence
from typing import cast

import numpy as np
import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.territories import (
    TerritoryCount,
    TerritoryPlan,
    TerritorySite,
)
from vcmi_mapgen.core.steps.terrain_gen.homes import room_side, room_tiles
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency
from vcmi_mapgen.core.steps.terrain_gen.places import PlacesTerrain
from vcmi_mapgen.core.steps.terrain_gen.planned import (
    PlannedFront,
    choose_plan,
    grow_territories,
    partition,
    plan_sites,
    symmetric,
)
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.water import TopologyForm

SIZE = 72
PLAYERS = 2


def _land(size: int = SIZE) -> list[list[bool]]:
    return [[True] * size for _ in range(size)]


def _plans(priors: Priors) -> Sequence[TerritoryPlan]:
    return priors.territories[0].plans_by_map


def test_a_plan_seats_exactly_the_players_asked_for(priors: Priors) -> None:
    for seed in range(5):
        plan = choose_plan(_plans(priors), PLAYERS, SIZE * SIZE, stream(seed, "plan"))
        assert len({s.owner for s in plan.sites if s.owner is not None}) == PLAYERS


def test_no_plan_for_a_player_count_the_corpus_lacks_stops_with_the_count() -> None:
    plans = (TerritoryPlan(TerritoryCount(2, 100, 1), (TerritorySite(0.5, 0.5, 1.0, 0),)),)
    with pytest.raises(ValueError, match="3 players"):
        _ = choose_plan(plans, 3, 100, stream(1, "plan"))


def test_the_symmetries_are_eight_distinct_moves_of_the_square() -> None:
    images = {symmetric((0.2, 0.7), k) for k in range(8)}
    assert len(images) == 8
    assert all(0 <= v <= 1 for p in images for v in p)


def test_every_player_is_dealt_one_site_and_sites_stay_on_the_square(priors: Priors) -> None:
    plan = choose_plan(_plans(priors), PLAYERS, SIZE * SIZE, stream(2, "plan"))
    sites = plan_sites(plan, PLAYERS, 2)
    assert sorted(s.owner for s in sites if s.owner is not None) == list(range(PLAYERS))
    assert all(0 <= v <= 1 for s in sites for v in s.point)


def test_each_place_lies_in_one_territory_and_each_player_is_home_in_its_own(
    priors: Priors,
) -> None:
    stats, spread = priors.places[0], priors.territories[0]
    for seed in (1, 2, 3):
        mask = np.array(_land(), dtype=np.bool_)
        plan = choose_plan(spread.plans_by_map, PLAYERS, SIZE * SIZE, stream(seed, "plan"))
        sites = plan_sites(plan, PLAYERS, seed)
        label, snapped, _ = partition(mask, sites, seed)
        draw = PlannedFront().draw(_land(), (stats, spread), SIZE * SIZE, seed, TerrainOptions())
        again = PlannedFront().draw(_land(), (stats, spread), SIZE * SIZE, seed, TerrainOptions())
        assert draw == again
        _, cells = grow_territories(label, len(sites), [SIZE * SIZE // 4], seed)
        assert len(cells) >= len(sites)
        seen: dict[int, set[int]] = {}
        for y, row in enumerate(draw.layout.label):
            for x, p in enumerate(row):
                seen.setdefault(p, set()).add(cast("int", label[y, x]))
        assert all(len(c) == 1 for p, c in seen.items() if p >= 0)
        assert sorted(p for p in draw.owners if p is not None) == list(range(PLAYERS))
        for player, (place, point) in enumerate(
            zip(draw.homes.places, draw.homes.points, strict=True)
        ):
            assert draw.owners[place] == player
            home_cell = next(iter(seen[place]))
            assert home_cell == cast("int", label[point[1], point[0]])
            owned = [i for i, s in enumerate(sites) if s.owner == player]
            assert owned == [home_cell]
            assert snapped[home_cell] is not None
        assert label_adjacency(draw.layout.label)


def test_the_room_of_a_home_lies_in_its_territory_where_one_fits(priors: Priors) -> None:
    stats, spread = priors.places[0], priors.territories[0]
    mask = np.array(_land(), dtype=np.bool_)
    plan = choose_plan(spread.plans_by_map, PLAYERS, SIZE * SIZE, stream(1, "plan"))
    label, _, _ = partition(mask, plan_sites(plan, PLAYERS, 1), 1)
    draw = PlannedFront().draw(_land(), (stats, spread), SIZE * SIZE, 1, TerrainOptions())
    for x, y in draw.homes.points:
        cell = cast("int", label[y, x])
        room = room_tiles((x, y), room_side())
        assert all(
            cast("int", label[ty, tx]) == cell
            for tx, ty in room
            if 0 <= tx < SIZE and 0 <= ty < SIZE
        )


def test_the_planned_model_draws_the_same_map_for_the_same_seed(
    catalog: Catalog, priors: Priors
) -> None:
    options = TerrainOptions(size=SIZE, players=PLAYERS)
    first = PlacesTerrain(TopologyForm(), PlannedFront()).draw(catalog, priors, 3, options)
    again = PlacesTerrain(TopologyForm(), PlannedFront()).draw(catalog, priors, 3, options)
    assert first.places == again.places
    assert first.grids == again.grids
    assert any("planned front" in line for line in first.log)
