"""Load and save the corpus count curves: the resource mines in ``data/pp/mines.json`` and the
towns in ``data/pp/towns.json``."""

from pathlib import Path

from vcmi_mapgen.core.priors.counts import CountCurve
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

MINES_FILE = "mines.json"
TOWNS_FILE = "towns.json"
CURVE_VERSION = 1
MINES_SOURCE = "vcmi_mapgen.corpus.mine.counts.mine_curve"
TOWNS_SOURCE = "vcmi_mapgen.corpus.mine.counts.town_curve"


def load_curve(pp_dir: Path, name: str) -> CountCurve:
    st = cache.read(pp_dir / name, version=CURVE_VERSION)
    return CountCurve(
        jv.as_float(st.get("intercept")),
        jv.as_float(st.get("land_exp")),
        jv.as_float(st.get("players_exp")),
    )


def save_curve(pp_dir: Path, name: str, source: str, curve: CountCurve) -> None:
    cache.write(
        pp_dir / name,
        source,
        {
            "_version": CURVE_VERSION,
            "intercept": curve.intercept,
            "land_exp": curve.land_exp,
            "players_exp": curve.players_exp,
        },
    )
