"""Reliability tests for core.steps.terrain_gen.macro (macro terrain generation)."""

from vcmi_mapgen.core.steps.terrain_gen import macro as MT


def test_macro_generate_deterministic_and_coarse() -> None:
    g1 = MT.generate(48, 48, seed=1)
    g2 = MT.generate(48, 48, seed=1)
    assert g1 == g2, "macro terrain must be seed-deterministic"
    rep = MT.report(g1)
    # the §4.3 gate: the macro layer must NOT fragment (the markov failure mode)
    assert rep.big_share >= 0.7, rep
