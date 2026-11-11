import random
from collections import Counter

import pytest

from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.priors.macro import MacroStats
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.identity import Palette, assign_dominants
from vcmi_mapgen.core.steps.terrain_gen.macro import pair_lifts

GRASS, DIRT = Terrain.GRASS, Terrain.DIRT


def _macro(adj: dict[str, int]) -> MacroStats:
    return MacroStats(
        areas=[], barrier_fracs=[], terr_share={GRASS.value: 60, DIRT.value: 40}, adj=adj, nzones=[]
    )


def test_a_region_of_many_places_draws_its_terrain_at_the_corpus_odds() -> None:
    stats = PlaceStats(dominant={PlaceRole.MIDDLE.value: {GRASS.value: 60, DIRT.value: 40}})
    palette = Palette([PlaceRole.MIDDLE] * 8, set(), [0] * 8)
    drawn = Counter(
        assign_dominants(palette, (stats, _macro({})), set(), random.Random(seed))[0]
        for seed in range(200)
    )
    assert drawn[GRASS] / 200 == pytest.approx(0.6, abs=0.1)


def test_terrains_bordering_at_their_shares_have_no_pull() -> None:
    adj = {f"{DIRT.value}|{DIRT.value}": 1600, f"{DIRT.value}|{GRASS.value}": 4800}
    adj[f"{GRASS.value}|{GRASS.value}"] = 3600
    lifts = pair_lifts(_macro(adj), [DIRT.value, GRASS.value])
    assert lifts[(DIRT.value, GRASS.value)] == pytest.approx(1.0, abs=0.01)
    assert lifts[(DIRT.value, DIRT.value)] == pytest.approx(1.0, abs=0.01)
