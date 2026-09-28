"""Per-terrain gameplay statistics: densities, sprite weights and covariate counts."""

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
