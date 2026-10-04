import contextlib
import io
import statistics
import time
from collections.abc import Mapping, Sequence

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import DEFAULT_TERRAIN, StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.reading.vector import Vector, map_vector
from vcmi_mapgen.core.reading.verdict import Spread, Verdict, columns, decide
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.mine.places import map_players
from vcmi_mapgen.corpus.priors import load_priors

SECONDS = "seconds"

type Columns = Mapping[str, Sequence[float]]


def _generated(catalog: Catalog, priors: Priors, config: StepConfig) -> Vector:
    pipeline = Pipeline(catalog, config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        state = pipeline.run()
    seconds = time.perf_counter() - start
    return {**map_vector(catalog, state, owners_of(state)), SECONDS: seconds}


def _corpus(catalog: Catalog, settings: Settings, size: int) -> list[Vector]:
    named = named_corpus_maps(settings.maps_dir)
    sized = [(name, state) for name, state in named if state.size == size] or named
    return [
        map_vector(catalog, state, map_players(settings.h3m_dir, name).owners)
        for name, state in sized
    ]


def _cell(spread: Spread | None) -> str:
    if spread is None:
        return "-"
    return f"{spread.median:.3f} [{spread.q1:.3f}, {spread.q3:.3f}]"


def _median(values: Sequence[float] | None) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


def table_lines(corpus: Columns, models: Mapping[str, Columns]) -> list[str]:
    """One row per reading: the corpus median and quartiles, then each model's median."""
    readings = list(corpus) + [r for cols in models.values() for r in cols if r not in corpus]
    readings = list(dict.fromkeys(readings))
    head = f"{'reading':22} {'corpus median [q1, q3]':28}" + "".join(f" {m:>9}" for m in models)
    rows = [
        f"{r:22} {_cell(Spread.of(corpus.get(r, ()))):28}"
        + "".join(f" {_median(cols.get(r)):>9}" for cols in models.values())
        for r in readings
    ]
    return [head, *rows]


def verdict_lines(candidate: str, baseline: str, verdict: Verdict) -> list[str]:
    """Whether ``candidate`` replaces ``baseline``, with the readings that decided it."""
    answer = "replaces" if verdict.switch else "does not replace"
    return [
        f"{candidate} {answer} {baseline}: closer on {len(verdict.closer)} of "
        + f"{len(verdict.comparisons)} readings ({', '.join(verdict.closer) or 'none'})",
        f"  worse than {baseline} by more than the corpus IQR: "
        + (", ".join(verdict.blockers) or "none"),
    ]


def readings(
    catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int, terrains: Sequence[str]
) -> None:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    models: dict[str, Columns] = {}
    for terrain in terrains:
        vectors = [
            _generated(catalog, priors, StepConfig(seed, size, terrain=terrain)) for seed in seeds
        ]
        models[terrain] = columns(vectors)
        print(f"generated {len(vectors)} maps with the {terrain} model")
    corpus_vectors = _corpus(catalog, settings, size)
    corpus = columns(corpus_vectors)
    print(f"read {len(corpus_vectors)} corpus maps")
    lines = table_lines(corpus, models)
    if DEFAULT_TERRAIN in models:
        for terrain, cols in models.items():
            if terrain != DEFAULT_TERRAIN:
                verdict = decide(corpus, cols, models[DEFAULT_TERRAIN], skip={SECONDS})
                lines += ["", *verdict_lines(terrain, DEFAULT_TERRAIN, verdict)]
    for line in lines:
        print(line)
