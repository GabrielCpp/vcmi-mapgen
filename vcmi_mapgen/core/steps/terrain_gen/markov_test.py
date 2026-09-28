"""Reliability tests for steps.terrain_gen.markov (corpus-learned terrain Markov chain)."""

import collections
from pathlib import Path

import pytest

from vcmi_mapgen.core.model import Cell, MapState
from vcmi_mapgen.core.steps.terrain_gen import markov as MT
from vcmi_mapgen.kit import pp_cache

type Table = collections.defaultdict[tuple[int, ...], collections.Counter[int]]


def _corpus_map(grid: list[list[int]]) -> MapState:
    m = MapState(size=len(grid))
    m.cells[0] = [[Cell(t=t) for t in row] for row in grid]
    return m


def _order(table: Table) -> list[tuple[tuple[int, ...], list[tuple[int, int]]]]:
    return [(k, list(c.items())) for k, c in table.items()]


def test_tables_round_trip_keeps_counter_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grid = [[3, 1, 3, 2], [1, 3, 2, 1], [2, 2, 1, 3], [3, 1, 1, 2]]
    maps = [_corpus_map(grid), _corpus_map([row[::-1] for row in grid])]
    tables = MT.MarkovTables(chain=MT.learn(0, maps), chain4=MT.learn4(0, maps))
    monkeypatch.setattr(pp_cache, "PP_DIR", tmp_path)
    MT.save_tables(0, tables)
    MT.load_tables.cache_clear()
    loaded = MT.load_tables(0)
    MT.load_tables.cache_clear()
    pairs: list[tuple[Table, Table]] = [
        (loaded.chain.full, tables.chain.full),
        (loaded.chain.pair, tables.chain.pair),
        (loaded.chain.one, tables.chain.one),
        (loaded.chain4.full, tables.chain4.full),
        (loaded.chain4.horiz, tables.chain4.horiz),
        (loaded.chain4.vert, tables.chain4.vert),
    ]
    for got, want in pairs:
        assert _order(got) == _order(want)
    assert list(loaded.chain.marg.items()) == list(tables.chain.marg.items())
    assert list(loaded.chain.marg) != sorted(loaded.chain.marg)


def test_missing_tables_name_mine_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pp_cache, "PP_DIR", tmp_path)
    MT.load_tables.cache_clear()
    with pytest.raises(pp_cache.MissingCacheError, match="mine-stats"):
        _ = MT.load_tables(0)
    MT.load_tables.cache_clear()
