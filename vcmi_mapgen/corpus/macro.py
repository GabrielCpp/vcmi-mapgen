"""Load and save the macro terrain statistics in ``data/pp/macro_stats.json`` and
``data/pp/macro_stats_underground.json``."""

from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.macro import MacroStats
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value

SOURCE = "vcmi_mapgen.corpus.mine.macro.mine_macro"


def _as_float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _stats_from_json(raw: JsonValue) -> MacroStats:
    obj = json_value.as_object(raw)
    return MacroStats(
        areas=[json_value.as_int(v) for v in json_value.as_list(obj.get("areas"))],
        barrier_fracs=[_as_float(v) for v in json_value.as_list(obj.get("barrier_fracs"))],
        terr_share={
            int(k): json_value.as_int(v)
            for k, v in json_value.as_object(obj.get("terr_share")).items()
        },
        adj={k: json_value.as_int(v) for k, v in json_value.as_object(obj.get("adj")).items()},
        nzones=[json_value.as_int(v) for v in json_value.as_list(obj.get("nzones"))],
    )


def _stats_to_json(st: MacroStats) -> dict[str, object]:
    return {
        "areas": st.areas,
        "barrier_fracs": st.barrier_fracs,
        "terr_share": {str(k): v for k, v in st.terr_share.items()},
        "adj": st.adj,
        "nzones": st.nzones,
    }


def _stats_path(pp_dir: Path, level: int) -> Path:
    return pp_dir / ("macro_stats.json" if level == 0 else "macro_stats_underground.json")


def load_macro(pp_dir: Path, level: int = 0) -> MacroStats:
    return _stats_from_json(cache.read(_stats_path(pp_dir, level)))


def save_macro(pp_dir: Path, level: int, st: MacroStats) -> None:
    cache.write(_stats_path(pp_dir, level), SOURCE, _stats_to_json(st))
