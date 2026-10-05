"""Print how the corpus and a few generated maps dress their small enclosed patches: how much
decoration covers them, how often they hold a counted object, which purposes those objects
serve, and how many maps stand a dwelling above the top creature tier."""

import contextlib
import io
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.reading.patches import Patch, map_cover, read_patches
from vcmi_mapgen.core.steps.gameplay.landmark import TOP_TIER
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.priors import load_priors

MIX = 8


@dataclass(slots=True)
class Tally:
    """What one side's maps hold: every patch, each map's land cover and the count of maps
    that stand a dwelling above the top tier."""

    maps: int = 0
    patches: list[Patch] = field(default_factory=list)
    covers: list[float] = field(default_factory=list)
    dragons: int = 0


def tally(catalog: Catalog, states: Sequence[MapState]) -> Tally:
    out = Tally()
    for state in states:
        out.maps += 1
        for level in sorted(state.terrain):
            out.patches += read_patches(state, level)
            cover = map_cover(state, level)
            if cover is not None:
                out.covers.append(cover)
        out.dragons += any((catalog.dwelling_level(o.kind) or 0) > TOP_TIER for o in state.objs)
    return out


def _spread(values: Sequence[float]) -> str:
    if len(values) < 2:
        return f"{values[0]:.2f}" if values else "-"
    q = statistics.quantiles(values, n=10)
    return f"{statistics.median(values):.2f} [{q[0]:.2f}, {q[-1]:.2f}]"


def _rows(side: Tally) -> list[str]:
    patches = side.patches
    held = sum(1 for p in patches if p.content)
    tiles = sum(p.tiles for p in patches)
    objects = sum(len(p.content) for p in patches)
    return [
        str(side.maps),
        f"{len(patches) / side.maps:.1f}" if side.maps else "-",
        _spread([p.cover for p in patches]),
        _spread(side.covers),
        f"{held / len(patches):.0%}" if patches else "-",
        f"{100 * objects / tiles:.2f}" if tiles else "-",
        f"{side.dragons} of {side.maps}",
    ]


LABELS = (
    "maps",
    "patches per map",
    "patch cover median [p10, p90]",
    "map cover median [p10, p90]",
    "patches with a counted object",
    "counted objects per 100 tiles",
    "maps with a dragon dwelling",
)


def _mix(side: Tally) -> Counter[str]:
    return Counter(purpose for p in side.patches for purpose in p.content)


def report_lines(corpus: Tally, generated: Tally) -> list[str]:
    """One row per reading with the corpus and the generated value, then each purpose's
    share of the counted objects inside patches."""
    head = f"{'reading':32} {'corpus':>20} {'generated':>20}"
    rows = [
        f"{label:32} {c:>20} {g:>20}"
        for label, c, g in zip(LABELS, _rows(corpus), _rows(generated), strict=True)
    ]
    mix_c, mix_g = _mix(corpus), _mix(generated)
    total_c, total_g = mix_c.total() or 1, mix_g.total() or 1
    order = [p for p, _ in (mix_c + mix_g).most_common(MIX)]
    mix = [f"{'  ' + p:32} {mix_c[p] / total_c:>20.0%} {mix_g[p] / total_g:>20.0%}" for p in order]
    return [head, *rows, "purpose share inside patches", *mix]


def _generated(catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int) -> Tally:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    states: list[MapState] = []
    for seed in seeds:
        pipeline = Pipeline(catalog, size)
        for _name, step in build_steps(priors, StepConfig(seed, size)):
            _ = pipeline.add_step(step)
        with contextlib.redirect_stdout(io.StringIO()):
            states.append(pipeline.run())
    return tally(catalog, states)


def patch_report(catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int) -> None:
    generated = _generated(catalog, settings, seeds, size)
    corpus = tally(catalog, [state for _name, state in named_corpus_maps(settings.maps_dir)])
    for line in report_lines(corpus, generated):
        print(line)
