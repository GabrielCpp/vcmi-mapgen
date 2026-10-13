"""Tests for the topology surface form."""

import random
from collections import Counter
from dataclasses import replace

import numpy as np

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.steps.terrain_gen.coastline import Shore
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.water import TopologyForm, walled_fronts, water_on_walls

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
