"""Tests for the corpus draws a places map starts from."""

import random

import pytest

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.place_draws import (
    HOME_FLOOR,
    SIZE_FLOOR,
    draw_roles,
    draw_sizes,
    place_count,
)
from vcmi_mapgen.core.steps.terrain_gen.streams import stream


@pytest.mark.parametrize(("players", "seed"), [(2, 1), (2, 2), (4, 1), (4, 3), (6, 5)])
def test_the_roles_put_one_home_per_player_first(priors: Priors, players: int, seed: int) -> None:
    stats = priors.places[0]
    n = place_count(stats.counts, players, 3900, stream(seed, "places"))
    roles = draw_roles(stats, n, players, stream(seed, "places"))
    assert len(roles) == n >= 2 * players + 1
    assert roles[:players] == [PlaceRole.HOME] * players
    assert PlaceRole.HOME not in roles[players:]


def test_the_sizes_keep_their_floors(priors: Priors) -> None:
    stats = priors.places[0]
    roles = draw_roles(stats, 12, 2, random.Random(3))
    sizes = draw_sizes(stats, roles, 3900, random.Random(3))
    assert all(s >= SIZE_FLOOR for s in sizes)
    assert all(s >= HOME_FLOOR for s, r in zip(sizes, roles, strict=True) if r == PlaceRole.HOME)


def test_the_same_seed_draws_the_same_roles_and_sizes(priors: Priors) -> None:
    def draw() -> tuple[list[PlaceRole], list[int]]:
        rng = stream(7, "places")
        roles = draw_roles(priors.places[0], 10, 2, rng)
        return roles, draw_sizes(priors.places[0], roles, 3900, rng)

    assert draw() == draw()
