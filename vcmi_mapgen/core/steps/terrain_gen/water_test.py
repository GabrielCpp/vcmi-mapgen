"""Tests for the topology surface form."""

import random
from collections import Counter
from dataclasses import replace

import numpy as np

from vcmi_mapgen.core.grid.noise import value_noise
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.steps.terrain_gen.coastline import Shore
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.water import (
    Flood,
    TopologyForm,
    walled_fronts,
    water_on_walls,
)

SIDE = 24


def _quarters() -> Layout:
    half = SIDE // 2
    label = [[(y >= half) * 2 + (x >= half) for x in range(SIDE)] for y in range(SIDE)]
    anchors = ((half // 2, half // 2), (half + half // 2, half // 2))
    return Layout(label, (*anchors, (half // 2, SIDE - 3), (SIDE - 3, SIDE - 3)), 4)


def _shore(keep: frozenset[tuple[int, int]] | None = None) -> Shore:
    doors = frozenset({(0, 1), (0, 2), (1, 3)})
    return Shore(_quarters(), (0, 1, 2, 3), doors, {}, keep or frozenset())


def test_the_land_is_all_land(priors: Priors) -> None:
    coast = TopologyForm().land(priors, 2, TerrainOptions(size=36, players=2))
    assert all(all(row) for row in coast.land)


def test_a_map_without_water_targets_floods_nothing(priors: Priors) -> None:
    dry = replace(priors, water=WaterPriors())
    layout, _ = TopologyForm().flood(_shore(), dry, 2, TerrainOptions(size=SIDE, players=2))
    assert layout == _quarters()


def test_walled_fronts_are_the_touching_territory_pairs_no_door_joins() -> None:
    label = np.array(_quarters().label, dtype=np.int64)
    walls = walled_fronts(label, (0, 1, 2, 3), [(0, 1), (0, 2), (1, 3)], {(2, 3): 3})
    assert walls == {(2, 3): 3}


def test_the_flood_lands_near_the_target_and_keeps_the_land_whole() -> None:
    keep = frozenset({(2, SIDE - 1), (SIDE - 2, SIDE - 1)})
    target = WaterTarget(0.15, 0.0, 1)
    layout, fronts = water_on_walls(_shore(keep), target, SIDE, random.Random(3))
    water = np.array(layout.label) < 0
    assert fronts == 1
    assert abs(float(np.mean(water)) - target.share) < 0.05
    assert not any(water[y, x] for x, y in keep)
    seen = {(x, y) for y in range(SIDE) for x in range(SIDE) if not water[y, x]}
    start = next(iter(seen))
    stack, reached = [start], {start}
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in seen and n not in reached:
                reached.add(n)
                stack.append(n)
    assert reached == seen


def test_the_flood_takes_no_more_than_half_of_a_place() -> None:
    target = WaterTarget(0.9, 0.0, 1)
    layout, _ = water_on_walls(_shore(), target, SIDE, random.Random(1))
    area = Counter(z for row in layout.label for z in row if z >= 0)
    assert all(area[z] * 2 >= (SIDE // 2) ** 2 for z in range(4))


def test_no_more_walled_fronts_take_water_than_the_target_has_masses() -> None:
    third = SIDE // 3
    label = [[(y // third) * 3 + x // third for x in range(SIDE)] for y in range(SIDE)]
    anchors = tuple((x * third + 4, y * third + 4) for y in range(3) for x in range(3))
    shore = Shore(Layout(label, anchors, 9), tuple(range(9)), frozenset(), {}, frozenset())
    for masses in (1, 2):
        target = WaterTarget(0.3, 0.0, masses)
        _, fronts = water_on_walls(shore, target, SIDE, random.Random(0))
        assert fronts == masses


def _one_piece(label: list[list[int]]) -> bool:
    cells = {(x, y) for y, row in enumerate(label) for x, z in enumerate(row) if z >= 0}
    start = next(iter(cells))
    stack, reached = [start], {start}
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in cells and n not in reached:
                reached.add(n)
                stack.append(n)
    return reached == cells


def test_a_coast_field_moves_the_coast_and_keeps_the_land_whole() -> None:
    third = SIDE // 3
    label = [[(y // third) * 3 + x // third for x in range(SIDE)] for y in range(SIDE)]
    anchors = tuple((x * third + 4, y * third + 4) for y in range(3) for x in range(3))
    shore = Shore(Layout(label, anchors, 9), tuple(range(9)), frozenset(), {}, frozenset())
    target = WaterTarget(0.3, 0.0, 2)
    plain, _ = water_on_walls(shore, target, SIDE, random.Random(0))
    field = 4 * np.asarray(value_noise(SIDE, SIDE, 4, random.Random(5)), dtype=np.float64)
    swayed, _ = water_on_walls(shore, target, SIDE, random.Random(0), field)
    assert swayed.label != plain.label
    assert _one_piece(swayed.label)
    area = Counter(z for row in swayed.label for z in row if z >= 0)
    assert all(area[z] * 2 >= third * third for z in range(9))


def test_a_splitting_flood_keeps_the_part_of_a_refused_piece_that_passes() -> None:
    label = np.zeros((6, 6), np.int64)
    keep = np.zeros((6, 6), np.bool_)
    piece = np.zeros((6, 6), np.bool_)
    piece[:4] = True
    whole = Flood(label.copy(), np.array([36]), keep)
    split = Flood(label.copy(), np.array([36]), keep, split=True)
    assert not whole.take(piece).any()
    taken = split.take(piece)
    assert 0 < np.count_nonzero(taken) <= 18
    assert np.count_nonzero(split.label >= 0) >= 18
