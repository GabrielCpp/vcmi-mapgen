"""Load and save the corpus resource mine curve in ``data/pp/mines.json``."""

from pathlib import Path

from vcmi_mapgen.core.priors.mines import MineCurve
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

MINES_FILE = "mines.json"
MINES_VERSION = 1
MINES_SOURCE = "vcmi_mapgen.corpus.mine.mines.mine_curve"


def load_mines(pp_dir: Path) -> MineCurve:
    st = cache.read(pp_dir / MINES_FILE, version=MINES_VERSION)
    return MineCurve(
        jv.as_float(st.get("intercept")),
        jv.as_float(st.get("land_exp")),
        jv.as_float(st.get("players_exp")),
    )


def save_mines(pp_dir: Path, curve: MineCurve) -> None:
    cache.write(
        pp_dir / MINES_FILE,
        MINES_SOURCE,
        {
            "_version": MINES_VERSION,
            "intercept": curve.intercept,
            "land_exp": curve.land_exp,
            "players_exp": curve.players_exp,
        },
    )
