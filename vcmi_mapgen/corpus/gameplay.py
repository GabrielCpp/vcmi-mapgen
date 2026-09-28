"""Load and save the per-terrain gameplay statistics in ``data/pp/gameplay_stats*.json``."""

from collections.abc import Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.gameplay import TerrainStats
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import json_value as jv

ROOT = project_root()


STATS_PATH = str(ROOT / "data" / "pp" / "gameplay_stats.json")


STATS_PATH_UNDERGROUND = str(ROOT / "data" / "pp" / "gameplay_stats_underground.json")


SOURCE = "vcmi_mapgen.core.steps.gameplay.mines.mine_gameplay"


STATS_VERSION = 5  # v5: border open fraction + full-front gate distances


def _number(value: JsonValue | None) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _int_map(value: JsonValue | None) -> dict[str, int]:
    return {k: jv.as_int(v) for k, v in jv.as_object(value).items()}


def _int_list(value: JsonValue | None) -> list[int]:
    return [jv.as_int(v) for v in jv.as_list(value)]


def _int_lists(value: JsonValue | None) -> dict[str, list[int]]:
    return {k: _int_list(v) for k, v in jv.as_object(value).items()}


def _stats_from_json(value: JsonValue | None) -> TerrainStats:
    d = jv.as_object(value)
    return TerrainStats(
        tiles=jv.as_int(d.get("tiles")),
        counts=_int_map(d.get("counts")),
        anim_w={k: _int_map(v) for k, v in jv.as_object(d.get("anim_w")).items()},
        e=_int_lists(d.get("e")),
        g=_int_lists(d.get("g")),
        o=_int_lists(d.get("o")),
        tiles_e=_int_list(d.get("tiles_e")),
        tiles_g=_int_list(d.get("tiles_g")),
        tiles_o=_int_list(d.get("tiles_o")),
        border_open_frac=_number(d.get("border_open_frac")),
        guard_frac={k: _number(v) for k, v in jv.as_object(d.get("guard_frac")).items()},
    )


def _stats_to_json(st: TerrainStats) -> dict[str, JsonValue]:
    return {
        "tiles": st.tiles,
        "counts": {k: v for k, v in st.counts.items()},
        "anim_w": {p: {a: n for a, n in c.items()} for p, c in st.anim_w.items()},
        "e": {p: [n for n in v] for p, v in st.e.items()},
        "g": {p: [n for n in v] for p, v in st.g.items()},
        "o": {p: [n for n in v] for p, v in st.o.items()},
        "tiles_e": [n for n in st.tiles_e],
        "tiles_g": [n for n in st.tiles_g],
        "tiles_o": [n for n in st.tiles_o],
        "border_open_frac": st.border_open_frac,
        "guard_frac": {p: f for p, f in st.guard_frac.items()},
    }


def _stats_path(level: int) -> Path:
    return Path(STATS_PATH if level == 0 else STATS_PATH_UNDERGROUND)


def load_gameplay(level: int = 0) -> dict[str, TerrainStats]:
    st = pp_cache.read(_stats_path(level), version=STATS_VERSION)
    return {k: _stats_from_json(v) for k, v in st.items() if k not in pp_cache.META_KEYS}


def save_gameplay(level: int, stats: Mapping[str, TerrainStats]) -> None:
    payload: dict[str, object] = {"_version": STATS_VERSION}
    for t, tst in stats.items():
        payload[t] = _stats_to_json(tst)
    pp_cache.write(_stats_path(level), SOURCE, payload)
