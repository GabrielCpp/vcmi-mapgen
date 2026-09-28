"""Zone segmentation + shape-intrinsic per-tile coordinates, composed for every caller that
needs "what zone is this tile in, and where within it" (the pipeline's SegmentStep and
the research tools)."""

import math
from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

from vcmi_mapgen.core.model import Cell, Tile, Zone
from vcmi_mapgen.kit import terrain_segment as TS


def canonical_coords(
    zones: Mapping[int, Zone], depth_arr: npt.NDArray[np.float32]
) -> dict[int, dict[Tile, tuple[float, float]]]:
    """Per-zone shape-intrinsic (depth, sweep) for every tile.

    depth = per-zone-renormalized BFS-to-boundary (0 edge .. 1 core); channel-20 is
            already /sqrt(area), so we renormalize to the zone's own [min,max].
    sweep = atan2(y-cy, x-cx) normalized to [0,1) (a cheap angular address).
    """
    out: dict[int, dict[Tile, tuple[float, float]]] = {}
    for zid, z in zones.items():
        tiles = z.tiles
        vals = [TS.at(depth_arr, x, y) for (x, y) in tiles]
        vmin, vmax = min(vals), max(vals)
        rng = vmax - vmin
        cx, cy = z.centroid
        m: dict[Tile, tuple[float, float]] = {}
        for x, y in tiles:
            raw = TS.at(depth_arr, x, y)
            depth = 0.5 if rng < 1e-9 else (raw - vmin) / rng
            sweep = (math.atan2(y - cy, x - cx) + math.pi) / (2 * math.pi)
            m[(x, y)] = (depth, sweep)
        out[zid] = m
    return out


def segment_level(
    lvl: list[list[Cell]],
) -> tuple[dict[int, Zone], list[list[int]], dict[int, dict[Tile, tuple[float, float]]]]:
    """segment + per-zone canonical coords for one terrain level."""
    zones, zone_label = TS.segment(lvl)
    feats = TS.compute_static_features(lvl, zones, zone_label)
    canon = canonical_coords(zones, feats[:, :, 20])
    return zones, zone_label, canon
