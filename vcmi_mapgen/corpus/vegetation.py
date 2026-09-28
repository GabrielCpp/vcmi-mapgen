"""Load and save the per-terrain vegetation statistics in ``data/pp/veg_<terrain>.json``."""

from collections.abc import Callable, Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.vegetation import CellStats, VegetationStats
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.formats import json_value

ROOT = project_root()
PP_DIR = str(ROOT / "data" / "pp")
SOURCE = "vcmi_mapgen.corpus.mine.vegetation.mine"


def _as_float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _int_list(value: JsonValue | None) -> list[int]:
    return [json_value.as_int(v) for v in json_value.as_list(value)]


def _float_list(value: JsonValue | None) -> list[float]:
    return [_as_float(v) for v in json_value.as_list(value)]


def _map_of[T](value: JsonValue | None, convert: Callable[[JsonValue], T]) -> dict[str, T]:
    return {k: convert(v) for k, v in json_value.as_object(value).items()}


def _stats_from_json(raw: JsonValue) -> VegetationStats:
    obj = json_value.as_object(raw)
    cell_obj = json_value.as_object(obj.get("cell"))
    cell = (
        CellStats(
            size=json_value.as_int(cell_obj.get("size")),
            n=json_value.as_int(cell_obj.get("n")),
            sum=json_value.as_int(cell_obj.get("sum")),
            sum2=json_value.as_int(cell_obj.get("sum2")),
        )
        if cell_obj
        else None
    )
    return VegetationStats(
        terrain=json_value.as_str(obj.get("terrain")),
        nzones=json_value.as_int(obj.get("nzones")),
        tiles=json_value.as_int(obj.get("tiles")),
        nanchors=json_value.as_int(obj.get("nanchors")),
        tiles_per_ebin=_int_list(obj.get("tiles_per_ebin")),
        anch=_map_of(obj.get("anch"), _int_list),
        lam=_map_of(obj.get("lam"), _float_list),
        lam_tot=_map_of(obj.get("lam_tot"), _as_float),
        g=_map_of(obj.get("g"), _float_list),
        pairN=_map_of(obj.get("pairN"), _int_list),
        pairD=_int_list(obj.get("pairD")),
        anim_w=_map_of(obj.get("anim_w"), lambda v: _map_of(v, json_value.as_int)),
        mean_blk_cells=_map_of(obj.get("mean_blk_cells"), _as_float),
        cell=cell,
        veg_blocked_frac=_as_float(obj.get("veg_blocked_frac")),
        runs=_map_of(obj.get("runs"), _as_float),
    )


def _stats_to_json(st: VegetationStats) -> dict[str, object]:
    return {
        "terrain": st.terrain,
        "nzones": st.nzones,
        "tiles": st.tiles,
        "nanchors": st.nanchors,
        "tiles_per_ebin": st.tiles_per_ebin,
        "anch": st.anch,
        "lam": st.lam,
        "lam_tot": st.lam_tot,
        "g": st.g,
        "pairN": st.pairN,
        "pairD": st.pairD,
        "anim_w": st.anim_w,
        "mean_blk_cells": st.mean_blk_cells,
        "cell": (
            None
            if st.cell is None
            else {"size": st.cell.size, "n": st.cell.n, "sum": st.cell.sum, "sum2": st.cell.sum2}
        ),
        "veg_blocked_frac": st.veg_blocked_frac,
        "runs": st.runs,
    }


def _stats_path(terrain: str) -> Path:
    return Path(PP_DIR) / f"veg_{terrain}.json"


def save_vegetation(stats: Mapping[str, VegetationStats]) -> None:
    for terr, st in stats.items():
        pp_cache.write(_stats_path(terr), SOURCE, _stats_to_json(st))


def load_vegetation(terrain: str) -> VegetationStats:
    return _stats_from_json(pp_cache.read(_stats_path(terrain)))


def vegetation_terrains() -> list[str]:
    """The terrain names that have saved vegetation statistics, sorted."""
    return sorted(p.stem.removeprefix("veg_") for p in Path(PP_DIR).glob("veg_*.json"))
