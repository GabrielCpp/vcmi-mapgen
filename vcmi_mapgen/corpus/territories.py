"""Load and save the corpus territory spread in ``data/pp/territory_stats.json``."""

from collections.abc import Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

TERRITORY_FILE = "territory_stats.json"
TERRITORY_VERSION = 2
TERRITORY_SOURCE = "vcmi_mapgen.corpus.mine.territories.mine_territories"
FIELDS = ("player_zones", "neutral_zones", "pair_doors")
BY_MAP = ("player_doors_by_map", "neutral_doors_by_map")


def _ints(value: JsonValue | None) -> tuple[int, ...]:
    return tuple(jv.as_int(v) for v in jv.as_list(value))


def _by_map(value: JsonValue | None) -> tuple[tuple[int, ...], ...]:
    return tuple(_ints(v) for v in jv.as_list(value))


def _stats(value: JsonValue) -> TerritoryStats:
    obj = jv.as_object(value)
    player_zones, neutral_zones, pair_doors = (_ints(obj.get(f)) for f in FIELDS)
    player_doors, neutral_doors = (_by_map(obj.get(f)) for f in BY_MAP)
    return TerritoryStats(player_zones, neutral_zones, pair_doors, player_doors, neutral_doors)


def load_territories(pp_dir: Path) -> dict[int, TerritoryStats]:
    st = cache.read(pp_dir / TERRITORY_FILE, version=TERRITORY_VERSION)
    return {int(lv): _stats(v) for lv, v in jv.as_object(st.get("levels")).items()}


def save_territories(pp_dir: Path, stats: Mapping[int, TerritoryStats]) -> None:
    cache.write(
        pp_dir / TERRITORY_FILE,
        TERRITORY_SOURCE,
        {
            "_version": TERRITORY_VERSION,
            "levels": {
                str(lv): {
                    "player_zones": list(st.player_zones),
                    "neutral_zones": list(st.neutral_zones),
                    "pair_doors": list(st.pair_doors),
                    "player_doors_by_map": [list(m) for m in st.player_doors_by_map],
                    "neutral_doors_by_map": [list(m) for m in st.neutral_doors_by_map],
                }
                for lv, st in stats.items()
            },
        },
    )
