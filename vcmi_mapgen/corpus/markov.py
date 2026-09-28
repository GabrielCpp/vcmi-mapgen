"""Load and save the terrain Markov tables in ``data/pp/markov_<level>.json``."""

import collections
import functools
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.markov import MarkovModel, MarkovModel4, MarkovTables
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

SOURCE = "vcmi_mapgen.corpus.mine.markov.learn, learn4"


type _Table[K] = collections.defaultdict[K, collections.Counter[int]]


def _counter_to_json(counter: collections.Counter[int]) -> list[list[int]]:
    return [[k, n] for k, n in counter.items()]


def _counter_from_json(raw: JsonValue) -> collections.Counter[int]:
    counter = collections.Counter[int]()
    for pair in jv.as_list(raw):
        k, n = jv.as_list(pair)
        counter[jv.as_int(k)] = jv.as_int(n)
    return counter


def _table_to_json[K: tuple[int, ...]](table: Mapping[K, collections.Counter[int]]) -> list[object]:
    return [[list(key), _counter_to_json(counter)] for key, counter in table.items()]


def _table_from_json[K: tuple[int, ...]](raw: JsonValue) -> _Table[K]:
    table: _Table[K] = collections.defaultdict(collections.Counter)
    for entry in jv.as_list(raw):
        key, counter = jv.as_list(entry)
        table[cast(K, tuple(jv.as_int(v) for v in jv.as_list(key)))] = _counter_from_json(counter)
    return table


def tables_path(pp_dir: Path, level: int) -> Path:
    return pp_dir / f"markov_{level}.json"


def save_tables(pp_dir: Path, level: int, tables: MarkovTables) -> None:
    chain, chain4 = tables.chain, tables.chain4
    cache.write(
        tables_path(pp_dir, level),
        SOURCE,
        {
            "full": _table_to_json(chain.full),
            "pair": _table_to_json(chain.pair),
            "one": _table_to_json(chain.one),
            "marg": _counter_to_json(chain.marg),
            "full4": _table_to_json(chain4.full),
            "horiz": _table_to_json(chain4.horiz),
            "vert": _table_to_json(chain4.vert),
        },
    )


@functools.cache
def load_tables(pp_dir: Path, level: int) -> MarkovTables:
    raw = cache.read(tables_path(pp_dir, level))
    chain = MarkovModel(
        full=_table_from_json(raw.get("full")),
        pair=_table_from_json(raw.get("pair")),
        one=_table_from_json(raw.get("one")),
        marg=_counter_from_json(raw.get("marg")),
    )
    chain4 = MarkovModel4(
        full=_table_from_json(raw.get("full4")),
        horiz=_table_from_json(raw.get("horiz")),
        vert=_table_from_json(raw.get("vert")),
    )
    return MarkovTables(chain=chain, chain4=chain4)
