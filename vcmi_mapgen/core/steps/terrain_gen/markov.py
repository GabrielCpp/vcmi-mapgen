"""Terrain Markov chain LEARNED from the 159 real maps (the user's idea #1).

P(terrain[x,y] | left, up, up-left), estimated from real surface terrain, sampled
in raster order with back-off. This reproduces the real LOCAL texture (patch sizes,
coastlines, how terrains border each other) instead of arbitrary noise blobs.
"""

import collections
import functools
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import pp_cache
from vcmi_mapgen.vcmi.formats import json_value as jv

SOURCE = "vcmi_mapgen.core.steps.terrain_gen.markov.learn, learn4"


@dataclass(slots=True)
class MarkovModel:
    full: collections.defaultdict[tuple[int, int, int], collections.Counter[int]]
    pair: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    one: collections.defaultdict[tuple[int], collections.Counter[int]]
    marg: collections.Counter[int]


@dataclass(slots=True)
class MarkovModel4:
    full: collections.defaultdict[tuple[int, int, int, int], collections.Counter[int]]
    horiz: collections.defaultdict[tuple[int, int], collections.Counter[int]]
    vert: collections.defaultdict[tuple[int, int], collections.Counter[int]]


def learn(level_index: int, maps: Iterable[OR.FaithfulMap]) -> MarkovModel:
    """counts for P(center | left, up, upleft) over real maps at the given level."""
    full: collections.defaultdict[tuple[int, int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u,ul)->center
    pair: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u)->center
    one: collections.defaultdict[tuple[int], collections.Counter[int]] = collections.defaultdict(
        collections.Counter
    )  # (l,)->center
    marg: collections.Counter[int] = collections.Counter()
    for m in maps:
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[c.t for c in row] for row in g]
        for y in range(H):
            for x in range(W):
                c = T[y][x]
                marg[c] += 1
                lf = T[y][x - 1] if x > 0 else None
                u = T[y - 1][x] if y > 0 else None
                ul = T[y - 1][x - 1] if (x > 0 and y > 0) else None
                if lf is not None and u is not None and ul is not None:
                    full[(lf, u, ul)][c] += 1
                if lf is not None and u is not None:
                    pair[(lf, u)][c] += 1
                if lf is not None:
                    one[(lf,)][c] += 1
    return MarkovModel(full=full, pair=pair, one=one, marg=marg)


def sample(counter: collections.Counter[int], rnd: random.Random) -> int:
    tot = sum(counter.values())
    r = rnd.random() * tot
    acc = 0
    for k, v in counter.items():
        acc += v
        if r <= acc:
            return k
    return next(iter(counter))


def learn4(level_index: int, maps: Iterable[OR.FaithfulMap]) -> MarkovModel4:
    """P(center | left,up,right,down) for isotropic Gibbs, with back-off tables."""
    full: collections.defaultdict[tuple[int, int, int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,u,r,d)->c
    horiz: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (l,r)->c
    vert: collections.defaultdict[tuple[int, int], collections.Counter[int]] = (
        collections.defaultdict(collections.Counter)
    )  # (u,d)->c
    for m in maps:
        if level_index >= len(m.terrain):
            continue
        g = m.terrain[level_index]
        H = len(g)
        W = len(g[0])
        T = [[c.t for c in row] for row in g]
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                c = T[y][x]
                lf = T[y][x - 1]
                u = T[y - 1][x]
                r = T[y][x + 1]
                d = T[y + 1][x]
                full[(lf, u, r, d)][c] += 1
                horiz[(lf, r)][c] += 1
                vert[(u, d)][c] += 1
    return MarkovModel4(full=full, horiz=horiz, vert=vert)


@dataclass(frozen=True, slots=True)
class MarkovTables:
    chain: MarkovModel
    chain4: MarkovModel4


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


def tables_path(level: int) -> Path:
    return pp_cache.PP_DIR / f"markov_{level}.json"


def save_tables(level: int, tables: MarkovTables) -> None:
    chain, chain4 = tables.chain, tables.chain4
    pp_cache.write(
        tables_path(level),
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
def load_tables(level: int) -> MarkovTables:
    raw = pp_cache.read(tables_path(level))
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
