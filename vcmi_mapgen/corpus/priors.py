"""Load every prior one generation run reads, once, into a ``Priors`` value."""

from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.corpus.gameplay import load_gameplay
from vcmi_mapgen.corpus.gates import load_gate_stats
from vcmi_mapgen.corpus.macro import load_macro
from vcmi_mapgen.corpus.markov import load_tables
from vcmi_mapgen.corpus.vegetation import load_vegetation, vegetation_terrains

LEVELS = (0, 1)


def load_priors() -> Priors:
    """The terrain and gameplay statistics of both levels, the gate estimator, and the
    vegetation statistics of every terrain that has them."""
    return Priors(
        terrain={lv: TerrainPriors(load_macro(lv), load_tables(lv)) for lv in LEVELS},
        gameplay={lv: load_gameplay(lv) for lv in LEVELS},
        gates=load_gate_stats(),
        vegetation={t: load_vegetation(t) for t in vegetation_terrains()},
    )
