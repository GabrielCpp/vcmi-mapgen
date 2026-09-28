"""Reliability tests for the player towns GameplayStep places."""

import contextlib
import io

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.steps import GameplayStep, TerrainStep, VegetationStep


def _run_towns(
    catalog: Catalog, seed: int, size: int = 48, players: int = 2, subterrain: bool = True
) -> MapState:

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pipeline = Pipeline(catalog, size)
        _ = pipeline.add_step(
            TerrainStep(size=size, seed=seed, water_mode="normal", subterrain=subterrain)
        )
        _ = pipeline.add_step(VegetationStep(seed=seed, players=players))
        _ = pipeline.add_step(
            GameplayStep(seed=seed, players=players, size=size, subterrain=subterrain)
        )
        map_state = pipeline.run()
    return map_state


def test_every_player_gets_a_placed_start_town(catalog: Catalog) -> None:
    """Each requested player receives a real placed TOWN object, and no town twice."""
    state = _run_towns(catalog, seed=1)
    town_positions = {(o.x, o.y, o.level) for o in state.objs if o.purpose == Purpose.TOWN}
    starts = [(t.x, t.y, t.level) for t in state.player_towns]
    assert len(starts) == 2, f"only {len(starts)}/2 players got a start town"
    assert len(set(starts)) == len(starts)
    assert set(starts) <= town_positions


def test_player_towns_never_exceeds_players_requested(catalog: Catalog) -> None:
    """The top-up fallback must still cap at `players` — it must not hand out every spare
    neutral town on the map to a request for fewer players."""
    state = _run_towns(catalog, seed=1, players=1)
    assert len(state.player_towns) <= 1
