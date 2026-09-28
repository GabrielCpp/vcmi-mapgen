"""Load every prior one generation run reads, once, into a ``Priors`` value."""

from pathlib import Path

from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.corpus.gameplay import load_gameplay
from vcmi_mapgen.corpus.gates import load_gate_stats
from vcmi_mapgen.corpus.macro import load_macro
from vcmi_mapgen.corpus.markov import load_tables
from vcmi_mapgen.corpus.vegetation import load_vegetation, vegetation_terrains

LEVELS = (0, 1)


def load_priors(pp_dir: Path) -> Priors:
    """The terrain and gameplay statistics of both levels, the gate estimator, and the
    vegetation statistics of every terrain that has them, all read from ``pp_dir``."""
    return Priors(
        terrain={
            lv: TerrainPriors(load_macro(pp_dir, lv), load_tables(pp_dir, lv)) for lv in LEVELS
        },
        gameplay={lv: load_gameplay(pp_dir, lv) for lv in LEVELS},
        gates=load_gate_stats(pp_dir),
        vegetation={t: load_vegetation(pp_dir, t) for t in vegetation_terrains(pp_dir)},
    )
