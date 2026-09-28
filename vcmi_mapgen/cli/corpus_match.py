import contextlib
import io
from collections.abc import Sequence

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.corpus.maps import all_map_names, load_corpus_map
from vcmi_mapgen.corpus.match import bucket_report, corpus_tally, generated_tally, measure_report
from vcmi_mapgen.corpus.priors import load_priors
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog


def generate(priors: Priors, seed: int, size: int, subterrain: bool) -> MapState:
    pipeline = Pipeline(VcmiCatalog(), size)
    for _name, step in build_steps(priors, StepConfig(seed, size, subterrain=subterrain)):
        _ = pipeline.add_step(step)
    with contextlib.redirect_stdout(io.StringIO()):
        return pipeline.run()


def corpus_match(settings: Settings, seeds: Sequence[int], size: int, subterrain: bool) -> None:
    maps_dir = settings.maps_dir
    corpus = corpus_tally(load_corpus_map(maps_dir, name) for name in all_map_names(maps_dir))
    priors = load_priors(settings.pp_dir)
    gen = generated_tally(generate(priors, seed, size, subterrain) for seed in seeds)
    for line in (*measure_report(corpus, gen), "", *bucket_report(corpus, gen)):
        print(line)
