"""Load and save the fitted odds of water and the corpus water targets in
``data/pp/water.json``."""

from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

WATER_FILE = "water.json"
WATER_VERSION = 2
WATER_SOURCE = "vcmi_mapgen.corpus.mine.water.mine_water"


def _floats(value: JsonValue) -> tuple[float, ...]:
    return tuple(jv.as_float(n) for n in jv.as_list(value))


def _target(value: JsonValue) -> WaterTarget:
    obj = jv.as_object(value)
    return WaterTarget(
        jv.as_float(obj.get("share")),
        jv.as_float(obj.get("edge")),
        jv.as_int(obj.get("masses")),
        jv.as_float(obj.get("dress")),
    )


def load_water(pp_dir: Path) -> WaterPriors:
    st = cache.read(pp_dir / WATER_FILE, version=WATER_VERSION)
    return WaterPriors(
        _floats(st.get("beta")),
        _floats(st.get("static_beta")),
        tuple(_target(t) for t in jv.as_list(st.get("targets"))),
        tuple((str(k), jv.as_int(n)) for k, n in jv.as_object(st.get("dress_kinds")).items()),
    )


def save_water(pp_dir: Path, st: WaterPriors) -> None:
    cache.write(
        pp_dir / WATER_FILE,
        WATER_SOURCE,
        {
            "_version": WATER_VERSION,
            "beta": list(st.beta),
            "static_beta": list(st.static_beta),
            "targets": [
                {"share": t.share, "edge": t.edge, "masses": t.masses, "dress": t.dress}
                for t in st.targets
            ],
            "dress_kinds": dict(st.dress_kinds),
        },
    )
