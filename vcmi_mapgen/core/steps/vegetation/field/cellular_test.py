"""Tests for the cellular field that shapes a zone's vegetation."""

import random
from typing import cast

import numpy as np

from vcmi_mapgen.core.steps.vegetation.field.cellular import (
    MAX_COVERAGE,
    cellular_field,
    coverage_by_ebin,
    target_mask,
)


def test_cellular_field_is_deterministic_and_non_negative() -> None:
    a = cellular_field(20, 16, random.Random(4))
    b = cellular_field(20, 16, random.Random(4))
    assert a.shape == (16, 20)
    assert np.array_equal(a, b)
    assert bool((a >= 0).all())


def test_coverage_by_ebin_averages_to_target() -> None:
    profile = np.array([2.0, 1.0, 0.5])
    tiles = np.array([10, 30, 60], dtype=np.int64)
    cov = coverage_by_ebin(profile, tiles, 0.2)
    shares = cast(list[float], cov.tolist())
    assert abs(sum(c * n for c, n in zip(shares, (10, 30, 60), strict=True)) / 100 - 0.2) < 1e-9
    assert shares[0] > shares[1] > shares[2]
    assert max(cast(list[float], coverage_by_ebin(profile, tiles, 5.0).tolist())) == MAX_COVERAGE


def test_target_mask_hits_coverage_and_keeps_forced_tiles() -> None:
    field = cellular_field(30, 30, random.Random(2))
    dom = np.ones((30, 30), dtype=np.bool_)
    ebins = np.zeros((30, 30), dtype=np.int8)
    forced = np.zeros((30, 30), dtype=np.bool_)
    forced[0, :] = True
    mask = target_mask(field, dom, ebins, np.array([0.3]), forced)
    assert bool(mask[0, :].all())
    free_share = cast(int, mask[1:, :].sum()) / (29 * 30)
    assert abs(free_share - 0.3) < 0.02
