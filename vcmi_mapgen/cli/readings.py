import contextlib
import io
import statistics
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.mines import land_area
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.reading.spread import Spread, columns
from vcmi_mapgen.core.reading.vector import Vector, map_vector
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.mine.counts import map_mines, map_towns
from vcmi_mapgen.corpus.mine.places import map_players
from vcmi_mapgen.corpus.priors import load_priors

SECONDS = "seconds"
MINES = "resource mines"
CURVE = "mine curve"
TOWNS = "towns"
TOWN_CURVE = "town curve"

type Columns = Mapping[str, Sequence[float]]
type Named = tuple[str, MapState]


def count_reading(catalog: Catalog, state: MapState, players: int, priors: Priors) -> Vector:
    """The resource mines and the towns on ``state``, each beside its curve's expectation at
    the map's land and ``players``."""
    land = land_area(state)
    return {
        MINES: float(map_mines(catalog, state)),
        CURVE: priors.mines.expected(land, players),
        TOWNS: float(map_towns(catalog, state)),
        TOWN_CURVE: priors.towns.expected(land, players),
    }


def count_line(seed: int, vector: Vector) -> str:
    """One generated map's resource mines and towns, each beside its curve's expectation."""
    mines, curve = vector[MINES], vector[CURVE]
    towns, town_curve = vector[TOWNS], vector[TOWN_CURVE]
    return (
        f"seed {seed}: {mines:.0f} resource mines, curve {curve:.1f}, ratio {mines / curve:.2f};"
        f" {towns:.0f} towns, curve {town_curve:.1f}, ratio {towns / town_curve:.2f}"
    )


def _generated(catalog: Catalog, priors: Priors, config: StepConfig) -> Vector:
    pipeline = Pipeline(catalog, config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        state = pipeline.run()
    seconds = time.perf_counter() - start
    counts = count_reading(catalog, state, config.players, priors)
    return {**map_vector(catalog, state, owners_of(state)), **counts, SECONDS: seconds}


def _corpus_vector(catalog: Catalog, h3m_dir: Path, priors: Priors, named: Named) -> Vector:
    name, state = named
    players = map_players(h3m_dir, name)
    counts = count_reading(catalog, state, players.players, priors)
    return {**map_vector(catalog, state, players.owners), **counts}


def _corpus(catalog: Catalog, settings: Settings, size: int, priors: Priors) -> list[Vector]:
    named = named_corpus_maps(settings.maps_dir)
    sized = [(name, state) for name, state in named if state.size == size] or named
    return [_corpus_vector(catalog, settings.h3m_dir, priors, n) for n in sized]


def _cell(spread: Spread | None) -> str:
    if spread is None:
        return "-"
    return f"{spread.median:.3f} [{spread.q1:.3f}, {spread.q3:.3f}]"


def _median(values: Sequence[float] | None) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


def table_lines(corpus: Columns, generated: Columns) -> list[str]:
    """One row per reading: the corpus median and quartiles, then the generated median."""
    readings = list(dict.fromkeys([*corpus, *generated]))
    head = f"{'reading':22} {'corpus median [q1, q3]':28} {'generated':>9}"
    rows = [
        f"{r:22} {_cell(Spread.of(corpus.get(r, ()))):28} {_median(generated.get(r)):>9}"
        for r in readings
    ]
    return [head, *rows]


def readings(catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int) -> None:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    vectors = [_generated(catalog, priors, StepConfig(seed, size)) for seed in seeds]
    generated = columns(vectors)
    print(f"generated {len(vectors)} maps")
    for seed, vector in zip(seeds, vectors, strict=True):
        print(count_line(seed, vector))
    corpus_vectors = _corpus(catalog, settings, size, priors)
    corpus = columns(corpus_vectors)
    print(f"read {len(corpus_vectors)} corpus maps")
    for line in table_lines(corpus, generated):
        print(line)
