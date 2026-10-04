"""Load and save the tiler tables in ``data/pp/tiler.json``. The export and the PNG renderer
read them. No step does."""

import collections
import functools
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.tiles import MaskTable, SigTable, TilerTables, ViewMirror

SOURCE = "vcmi_mapgen.corpus.mine.tiler.learn"


def _counts_to_json(counter: collections.Counter[ViewMirror]) -> list[list[int]]:
    return [[view, m, n] for (view, m), n in counter.items()]


def _counts_from_json(raw: JsonValue) -> collections.Counter[ViewMirror]:
    counter = collections.Counter[ViewMirror]()
    for entry in jv.as_list(raw):
        view, m, n = (jv.as_int(v) for v in jv.as_list(entry))
        counter[(view, m)] = n
    return counter


def _sig_table_from_json(raw: JsonValue) -> SigTable:
    table: SigTable = {}
    for entry in jv.as_list(raw):
        t, sig, counts = jv.as_list(entry)
        key = (jv.as_int(t), tuple(jv.as_int(v) for v in jv.as_list(sig)))
        table[key] = _counts_from_json(counts)
    return table


def _mask_table_from_json(raw: JsonValue) -> MaskTable:
    table: MaskTable = {}
    for entry in jv.as_list(raw):
        mask, counts = jv.as_list(entry)
        table[jv.as_int(mask)] = _counts_from_json(counts)
    return table


def tiler_path(pp_dir: Path) -> Path:
    return pp_dir / "tiler.json"


def save_tiler(pp_dir: Path, tables: TilerTables) -> None:
    cache.write(
        tiler_path(pp_dir),
        SOURCE,
        {
            "exact": [[t, list(sig), _counts_to_json(c)] for (t, sig), c in tables.exact.items()],
            "four": [[t, list(sig), _counts_to_json(c)] for (t, sig), c in tables.four.items()],
            "clean": [[t, _counts_to_json(c)] for t, c in tables.clean.items()],
            "road_exact": [[k, _counts_to_json(c)] for k, c in sorted(tables.road_exact.items())],
            "road_four": [[k, _counts_to_json(c)] for k, c in sorted(tables.road_four.items())],
        },
    )


@functools.cache
def load_tiler(pp_dir: Path) -> TilerTables:
    raw = cache.read(tiler_path(pp_dir))
    clean: dict[int, collections.Counter[ViewMirror]] = {}
    for entry in jv.as_list(raw.get("clean")):
        t, counts = jv.as_list(entry)
        clean[jv.as_int(t)] = _counts_from_json(counts)
    return TilerTables(
        _sig_table_from_json(raw.get("exact")),
        _sig_table_from_json(raw.get("four")),
        clean,
        _mask_table_from_json(raw.get("road_exact")),
        _mask_table_from_json(raw.get("road_four")),
    )
