"""Reliability tests for the vegetation prior fits."""

import math

from vcmi_mapgen.core.priors.vegetation import (
    RMAX,
    CellStats,
    VegetationStats,
    cox_sigma,
    theta_local,
)


def _stats(g: list[float], pairs: int, cell: CellStats | None) -> VegetationStats:
    return VegetationStats(
        terrain="grass",
        nzones=1,
        tiles=100,
        nanchors=10,
        tiles_per_ebin=[],
        anch={},
        lam={},
        lam_tot={},
        g={"tree|tree": g},
        pairN={"tree|tree": [pairs] * (RMAX + 1)},
        pairD=[],
        anim_w={},
        mean_blk_cells={},
        cell=cell,
        veg_blocked_frac=0.2,
        runs={},
    )


def test_theta_local_divides_by_the_mid_range_correlation() -> None:
    g = [4.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    want = [math.log(4.0), math.log(2.0), 0.0]
    assert theta_local(_stats(g, 100, None)) == {"tree|tree": want}
    assert theta_local(_stats(g, 5, None)) == {"tree|tree": [0.0, 0.0, 0.0]}


def test_cox_sigma_reads_the_cell_overdispersion() -> None:
    g = [1.0] * (RMAX + 1)
    assert cox_sigma(_stats(g, 100, None)) == 0.0
    assert cox_sigma(_stats(g, 100, CellStats(size=6, n=20, sum=40, sum2=80))) == 0.0
    sigma = cox_sigma(_stats(g, 100, CellStats(size=6, n=20, sum=40, sum2=200)))
    assert math.isclose(sigma, math.sqrt(math.log(1.0 + 2.0 / 2.0)))
