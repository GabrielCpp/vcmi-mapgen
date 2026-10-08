"""Tests for the topology surface form."""

import random
from dataclasses import replace

import numpy as np

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency
from vcmi_mapgen.core.steps.terrain_gen.water import (
    TopologyForm,
    bridge_tiles,
    masses_of,
    strait_tiles,
)

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


def test_a_bridge_keeps_a_walk_between_the_anchors_of_a_pair_on_one_mass() -> None:
    label = np.array([[0, 0, 0, 1, 1, 1]] * 5)
    forced = np.zeros(label.shape, dtype=np.bool_)
    kept = bridge_tiles(label, [(0, 2), (5, 2)], [(0, 1)], [0, 0], forced)
    assert kept.tolist() == [[False] * 6] + [[True] * 6] * 3 + [[False] * 6]
    assert not bridge_tiles(label, [(0, 2), (5, 2)], [(0, 1)], [0, 1], forced).any()


def test_a_bridge_detours_around_the_forced_water() -> None:
    label = np.array([[0, 0, 0, 1, 1, 1]] * 5)
    forced = np.zeros(label.shape, dtype=np.bool_)
    forced[1:, 2:4] = True
    kept = bridge_tiles(label, [(0, 4), (5, 4)], [(0, 1)], [0, 0], forced)
    assert kept[0, 2] and kept[0, 3]
    assert not (kept & forced).any()


def test_heavy_water_keeps_every_planned_border_on_one_mass(priors: Priors) -> None:
    target = WaterTarget(0.6, 0.5, 1)
    wet = replace(priors, water=replace(priors.water, targets=(target,)))
    for seed in (1, 2, 3):
        coast = TopologyForm().form(wet, seed, TerrainOptions(size=48, players=2))
        cut = coast.graph.edges - label_adjacency(coast.layout.label)
        assert cut <= coast.layout.missing
