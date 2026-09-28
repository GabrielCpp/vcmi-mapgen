import contextlib
import io
from collections.abc import Sequence

from vcmi_mapgen.cli.steps import build_steps
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.corpus.match import bucket_report, corpus_tally, generated_tally, measure_report
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog


def generate(seed: int, size: int, subterrain: bool) -> MapState:
    pipeline = Pipeline(VcmiCatalog(), size)
    for _name, step in build_steps(seed, size, 2, "normal", subterrain):
        _ = pipeline.add_step(step)
    with contextlib.redirect_stdout(io.StringIO()):
        return pipeline.run()


def corpus_match(seeds: Sequence[int], size: int, subterrain: bool) -> None:
    corpus = corpus_tally()
    gen = generated_tally(generate(seed, size, subterrain) for seed in seeds)
    for line in (*measure_report(corpus, gen), "", *bucket_report(corpus, gen)):
        print(line)
