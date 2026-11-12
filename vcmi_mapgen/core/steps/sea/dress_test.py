import random

from vcmi_mapgen.core.model import Footprint, Identity, Role, Tile
from vcmi_mapgen.core.steps.sea.dress import SeaLevel, dress_level, keeps_sea

_ROCK = Identity("rock", "rock", "avlrk1w0", Footprint.one(Role.BLOCKING))


def _sea(w: int, h: int) -> frozenset[Tile]:
    return frozenset((x, y) for x in range(w) for y in range(h))


_NONE: frozenset[Tile] = frozenset()


def _level(water: frozenset[Tile], rate: float, visits: frozenset[Tile] = _NONE) -> SeaLevel:
    return SeaLevel(0, water, frozenset(), frozenset(), visits, rate)


def testkeeps_sea_refuses_a_rock_that_cuts_a_strait() -> None:
    strait = {(x, 0) for x in range(3)}
    assert not keeps_sea(strait, {(1, 0)})


def testkeeps_sea_allows_a_rock_in_open_water() -> None:
    assert keeps_sea(set(_sea(3, 3)), {(1, 1)})


def test_dress_reaches_the_goal_on_open_water() -> None:
    water = _sea(20, 20)
    objs = dress_level(_level(water, 0.1), [(_ROCK, 1.0)], random.Random("t"))
    assert len(objs) == 40


def test_dress_never_blocks_beside_a_visit_cell() -> None:
    water = _sea(10, 10)
    visit = (5, 5)
    objs = dress_level(_level(water, 0.5, frozenset({visit})), [(_ROCK, 1.0)], random.Random("v"))
    assert objs
    assert all(max(abs(o.x - visit[0]), abs(o.y - visit[1])) > 1 for o in objs)


def test_dress_never_splits_a_narrow_sea() -> None:
    water = frozenset({(x, y) for x in range(12) for y in range(2)})
    objs = dress_level(_level(water, 0.5), [(_ROCK, 1.0)], random.Random("s"))
    left = set(water) - {(o.x, o.y) for o in objs}
    start = next(iter(left))
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for t in ((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            if t in left and t not in seen:
                seen.add(t)
                stack.append(t)
    assert objs
    assert seen == left
