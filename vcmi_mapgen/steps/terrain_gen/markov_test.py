"""Reliability tests for steps.terrain_gen.markov (corpus-learned terrain Markov chain)."""

import collections
import os as os_module

import pytest

from vcmi_mapgen.steps.terrain_gen import markov as MT

Tables = collections.defaultdict[tuple[int, ...], collections.Counter[int]]


def test_learn_is_independent_of_listdir_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """learn()/learn4() must sort the corpus file list themselves: `OR.all_map_names()`'s
    underlying os.listdir() order is filesystem-dependent (directory-listing order), and
    _sample() picks an outcome by walking a Counter in INSERTION order against a random
    threshold — the totals are order-invariant, but which key a given draw lands on is
    not. Two checkouts of the same repo (or two runs on different machines) could
    otherwise generate a different map for the identical seed. Regression for the bug
    fixed by sorting the corpus file list (formerly glob.glob(), now os.listdir())."""
    real_listdir = os_module.listdir

    def reversed_listdir(path: str) -> list[str]:
        return list(reversed(real_listdir(path)))

    m1 = MT.learn(0)
    monkeypatch.setattr(os_module, "listdir", reversed_listdir)
    m2 = MT.learn(0)

    tables: list[tuple[str, Tables, Tables]] = [
        ("full", m1.full, m2.full),
        ("pair", m1.pair, m2.pair),
        ("one", m1.one, m2.one),
    ]
    for key, d1, d2 in tables:
        assert set(d1) == set(d2)
        for k in d1:
            # exact insertion-order equality, not just Counter value-equality (a Counter
            # compares as a plain mapping — order-blind — so this must check the
            # iteration order _sample() actually walks).
            assert list(d1[k].items()) == list(d2[k].items()), (
                f"learn()['{key}'][{k!r}] iteration order depends on directory-listing "
                "order — the corpus file list must be sorted before scanning"
            )
    assert list(m1.marg.items()) == list(m2.marg.items())


def test_learn4_is_independent_of_listdir_order(monkeypatch: pytest.MonkeyPatch) -> None:
    real_listdir = os_module.listdir

    def reversed_listdir(path: str) -> list[str]:
        return list(reversed(real_listdir(path)))

    m1 = MT.learn4(0)
    monkeypatch.setattr(os_module, "listdir", reversed_listdir)
    m2 = MT.learn4(0)

    tables: list[tuple[str, Tables, Tables]] = [
        ("full", m1.full, m2.full),
        ("horiz", m1.horiz, m2.horiz),
        ("vert", m1.vert, m2.vert),
    ]
    for key, d1, d2 in tables:
        assert set(d1) == set(d2)
        for k in d1:
            assert list(d1[k].items()) == list(d2[k].items()), (
                f"learn4()['{key}'][{k!r}] iteration order depends on directory-listing "
                "order — the corpus file list must be sorted before scanning"
            )
