"""Per-terrain gameplay statistics: densities, sprite weights and covariate counts."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerrainStats:
    tiles: int
    counts: dict[str, int]
    anim_w: dict[str, dict[str, int]]
    e: dict[str, list[int]]
    g: dict[str, list[int]]
    o: dict[str, list[int]]
    tiles_e: list[int]
    tiles_g: list[int]
    tiles_o: list[int]
    border_open_frac: float
    guard_frac: dict[str, float]


type GameplayStats = Mapping[str, TerrainStats]
"""The gameplay statistics of one terrain level, keyed by terrain name."""


HEMMED_SHARE = 0.67
"""The corpus share of towns, mines, dwellings, banks and visited objects whose sprite has a
closed tile on both flanks."""

SNUG_FLOOR: Mapping[int, float] = {1: 0.62, 2: 0.58, 3: 0.82}
"""Per size class, the snug share nine corpus maps in ten reach: one-tile objects in a hole or
a corner, two-tile objects backed past their far end, larger objects backed above their top."""
