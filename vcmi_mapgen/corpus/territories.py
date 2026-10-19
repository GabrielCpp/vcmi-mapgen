"""Load and save the corpus territory spread in ``data/pp/territory_stats.json``."""

from collections.abc import Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.territories import (
    TerritoryCount,
    TerritoryPlan,
    TerritorySite,
    TerritoryStats,
)
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

TERRITORY_FILE = "territory_stats.json"
TERRITORY_VERSION = 8
TERRITORY_SOURCE = "vcmi_mapgen.corpus.mine.territories.mine_territories"
BY_MAP = ("player_doors_by_map", "neutral_doors_by_map")
COUNTS = "counts_by_map"
PLANS = "plans_by_map"
COUNT_FIELDS = ("players", "land", "territories")


def _ints(value: JsonValue | None) -> tuple[int, ...]:
    return tuple(jv.as_int(v) for v in jv.as_list(value))


def _by_map(value: JsonValue | None) -> tuple[tuple[int, ...], ...]:
    return tuple(_ints(v) for v in jv.as_list(value))


def _site(value: JsonValue) -> TerritorySite:
    obj = jv.as_object(value)
    owner = obj.get("owner")
    return TerritorySite(
        jv.as_float(obj.get("x")),
        jv.as_float(obj.get("y")),
        jv.as_float(obj.get("share")),
        None if owner is None else jv.as_int(owner),
    )


def _plan(value: JsonValue) -> TerritoryPlan:
    obj = jv.as_object(value)
    sites = tuple(_site(v) for v in jv.as_list(obj.get("sites")))
    return TerritoryPlan(_count(obj.get("record")), sites)


def _count(value: JsonValue | None) -> TerritoryCount:
    obj = jv.as_object(value)
    players, land, territories = (jv.as_int(obj.get(f)) for f in COUNT_FIELDS)
    homes = _ints(obj.get("homes"))
    area, prizes = jv.as_int(obj.get("area")), jv.as_int(obj.get("prizes"))
    return TerritoryCount(players, land, territories, homes, area, prizes)


def _stats(value: JsonValue) -> TerritoryStats:
    obj = jv.as_object(value)
    pair_doors = _ints(obj.get("pair_doors"))
    player_doors, neutral_doors = (_by_map(obj.get(f)) for f in BY_MAP)
    counts = tuple(_count(v) for v in jv.as_list(obj.get(COUNTS)))
    plans = tuple(_plan(v) for v in jv.as_list(obj.get(PLANS)))
    return TerritoryStats(pair_doors, player_doors, neutral_doors, counts, plans)


def load_territories(pp_dir: Path) -> dict[int, TerritoryStats]:
    st = cache.read(pp_dir / TERRITORY_FILE, version=TERRITORY_VERSION)
    return {int(lv): _stats(v) for lv, v in jv.as_object(st.get("levels")).items()}


def _count_json(c: TerritoryCount) -> dict[str, object]:
    return {
        "players": c.players,
        "land": c.land,
        "territories": c.territories,
        "homes": list(c.homes),
        "area": c.area,
        "prizes": c.prizes,
    }


def save_territories(pp_dir: Path, stats: Mapping[int, TerritoryStats]) -> None:
    cache.write(
        pp_dir / TERRITORY_FILE,
        TERRITORY_SOURCE,
        {
            "_version": TERRITORY_VERSION,
            "levels": {
                str(lv): {
                    "pair_doors": list(st.pair_doors),
                    "player_doors_by_map": [list(m) for m in st.player_doors_by_map],
                    "neutral_doors_by_map": [list(m) for m in st.neutral_doors_by_map],
                    COUNTS: [_count_json(c) for c in st.counts_by_map],
                    PLANS: [
                        {
                            "record": _count_json(p.record),
                            "sites": [
                                {"x": t.x, "y": t.y, "share": t.share, "owner": t.owner}
                                for t in p.sites
                            ],
                        }
                        for p in st.plans_by_map
                    ],
                }
                for lv, st in stats.items()
            },
        },
    )
