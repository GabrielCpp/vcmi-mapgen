"""Tests for the place graph a places map starts from."""

import collections

import pytest

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph, draw_graph
from vcmi_mapgen.core.steps.terrain_gen.streams import stream


def _connected(graph: PlaceGraph) -> bool:
    nbr: dict[int, set[int]] = collections.defaultdict(set)
    for a, b in graph.edges:
        nbr[a].add(b)
        nbr[b].add(a)
    seen = {0}
    todo = [0]
    while todo:
        for v in nbr[todo.pop()] - seen:
            seen.add(v)
            todo.append(v)
    return len(seen) == len(graph.roles)


@pytest.mark.parametrize(("players", "seed"), [(2, 1), (2, 2), (4, 1), (4, 3), (6, 5)])
def test_the_graph_is_connected_with_one_home_per_player(
    priors: Priors, players: int, seed: int
) -> None:
    graph = draw_graph(priors.places[0], players, 3900, stream(seed, "places"))
    homes = [i for i, r in enumerate(graph.roles) if r == PlaceRole.HOME]
    assert _connected(graph)
    assert len(homes) == players
    assert [graph.owners[h] for h in homes] == homes
    assert all(graph.owners[i] is None for i in range(len(graph.roles)) if i not in homes)
    assert not any(a in homes and b in homes for a, b in graph.edges)


def test_the_same_seed_draws_the_same_graph(priors: Priors) -> None:
    def draw() -> PlaceGraph:
        return draw_graph(priors.places[0], 2, 3900, stream(7, "places"))

    assert draw() == draw()
