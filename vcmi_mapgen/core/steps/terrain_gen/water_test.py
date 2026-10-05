"""Tests for the topology surface form."""

import random
from dataclasses import replace

import numpy as np

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph
from vcmi_mapgen.core.steps.terrain_gen.water import TopologyForm, masses_of, strait_tiles

H, T = PlaceRole.HOME, PlaceRole.TREASURE


def test_each_home_seeds_its_own_mass_and_every_place_joins_one() -> None:
    graph = PlaceGraph(
        (H, T, T, H), (0, None, None, 1), (10, 10, 10, 10), frozenset({(0, 1), (1, 2), (2, 3)})
    )
    mass = masses_of(graph, 2, random.Random(1))
    assert mass[0] != mass[3]
    assert mass == [mass[0], mass[0], mass[3], mass[3]]


def test_a_strait_runs_along_both_sides_of_a_mass_border() -> None:
    grid = np.array([[0, 0, 1, 1]] * 3)
    assert strait_tiles(grid).tolist() == [[False, True, True, False]] * 3


def test_a_map_without_water_targets_stays_all_land(priors: Priors) -> None:
    dry = replace(priors, water=WaterPriors())
    coast = TopologyForm().form(dry, 2, TerrainOptions(size=36, players=2))
    assert all(z >= 0 for row in coast.layout.label for z in row)


def test_the_drawn_share_lands_near_the_target(priors: Priors) -> None:
    target = WaterTarget(0.3, 0.5, 1)
    wet = replace(priors, water=replace(priors.water, targets=(target,)))
    coast = TopologyForm().form(wet, 2, TerrainOptions(size=48, players=2))
    share = np.mean(np.array(coast.layout.label) < 0)
    assert abs(share - target.share) < 0.05
