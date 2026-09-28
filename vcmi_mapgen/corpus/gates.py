"""Load and save the corpus gate estimator in ``data/pp/gate_stats.json``."""

from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import json_value as jv

ROOT = project_root()


GATE_STATS_PATH = ROOT / "data" / "pp" / "gate_stats.json"


GATE_STATS_VERSION = 2


GATE_STATS_SOURCE = "vcmi_mapgen.corpus.mine.gates.mine_gate_stats"


def load_gate_stats() -> GateStats:
    st = pp_cache.read(GATE_STATS_PATH, version=GATE_STATS_VERSION)
    frac = st.get("min_gap_frac")
    return GateStats(
        counts_by_size={
            int(w): tuple(jv.as_int(n) for n in jv.as_list(ns))
            for w, ns in jv.as_object(st.get("counts_by_size")).items()
        },
        min_gap_frac=float(frac) if isinstance(frac, int | float) else 0.0,
        n_maps=jv.as_int(st.get("n_maps")),
    )


def save_gate_stats(st: GateStats) -> None:
    pp_cache.write(
        GATE_STATS_PATH,
        GATE_STATS_SOURCE,
        {
            "_version": GATE_STATS_VERSION,
            "counts_by_size": {str(w): list(ns) for w, ns in st.counts_by_size.items()},
            "min_gap_frac": st.min_gap_frac,
            "n_maps": st.n_maps,
        },
    )
