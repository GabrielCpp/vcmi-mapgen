"""Load and save the corpus gate estimator in ``data/pp/gate_stats.json``."""

from pathlib import Path

from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

GATE_STATS_FILE = "gate_stats.json"


GATE_STATS_VERSION = 2


GATE_STATS_SOURCE = "vcmi_mapgen.corpus.mine.gates.mine_gate_stats"


def load_gate_stats(pp_dir: Path) -> GateStats:
    st = cache.read(pp_dir / GATE_STATS_FILE, version=GATE_STATS_VERSION)
    frac = st.get("min_gap_frac")
    return GateStats(
        counts_by_size={
            int(w): tuple(jv.as_int(n) for n in jv.as_list(ns))
            for w, ns in jv.as_object(st.get("counts_by_size")).items()
        },
        min_gap_frac=float(frac) if isinstance(frac, int | float) else 0.0,
        n_maps=jv.as_int(st.get("n_maps")),
    )


def save_gate_stats(pp_dir: Path, st: GateStats) -> None:
    cache.write(
        pp_dir / GATE_STATS_FILE,
        GATE_STATS_SOURCE,
        {
            "_version": GATE_STATS_VERSION,
            "counts_by_size": {str(w): list(ns) for w, ns in st.counts_by_size.items()},
            "min_gap_frac": st.min_gap_frac,
            "n_maps": st.n_maps,
        },
    )
