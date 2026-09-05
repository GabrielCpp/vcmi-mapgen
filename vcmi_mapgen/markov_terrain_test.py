"""Reliability tests for markov_terrain (corpus-learned terrain Markov chain)."""


def test_learn_is_independent_of_listdir_order(monkeypatch):
    """learn()/learn4() must sort the corpus file list themselves: `OR.all_map_names()`'s
    underlying os.listdir() order is filesystem-dependent (directory-listing order), and
    _sample() picks an outcome by walking a Counter in INSERTION order against a random
    threshold — the totals are order-invariant, but which key a given draw lands on is
    not. Two checkouts of the same repo (or two runs on different machines) could
    otherwise generate a different map for the identical seed. Regression for the bug
    fixed by sorting the corpus file list (formerly glob.glob(), now os.listdir())."""
    import os as os_module

    from vcmi_mapgen import markov_terrain as MT

    real_listdir = os_module.listdir

    def reversed_listdir(path):
        return list(reversed(real_listdir(path)))

    m1 = MT.learn(0)
    monkeypatch.setattr(os_module, "listdir", reversed_listdir)
    m2 = MT.learn(0)

    for key in ("full", "pair", "one"):
        d1, d2 = m1[key], m2[key]
        assert set(d1) == set(d2)
        for k in d1:
            # exact insertion-order equality, not just Counter value-equality (a Counter
            # compares as a plain mapping — order-blind — so this must check the
            # iteration order _sample() actually walks).
            assert list(d1[k].items()) == list(d2[k].items()), (
                f"learn()['{key}'][{k!r}] iteration order depends on directory-listing "
                "order — the corpus file list must be sorted before scanning")
    assert list(m1["marg"].items()) == list(m2["marg"].items())


def test_learn4_is_independent_of_listdir_order(monkeypatch):
    import os as os_module

    from vcmi_mapgen import markov_terrain as MT

    real_listdir = os_module.listdir

    def reversed_listdir(path):
        return list(reversed(real_listdir(path)))

    m1 = MT.learn4(0)
    monkeypatch.setattr(os_module, "listdir", reversed_listdir)
    m2 = MT.learn4(0)

    for key in ("full", "horiz", "vert"):
        d1, d2 = m1[key], m2[key]
        assert set(d1) == set(d2)
        for k in d1:
            assert list(d1[k].items()) == list(d2[k].items()), (
                f"learn4()['{key}'][{k!r}] iteration order depends on directory-listing "
                "order — the corpus file list must be sorted before scanning")
