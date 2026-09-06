"""MapState — the render-only view of a finished VCMI map."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MapState:
    """The narrow, render-only view of a finished map: exactly what PngRenderer,
    MapOverlay and VmapRenderer read, and nothing else.

    A field belongs here only if it describes the map itself as VCMI means it --
    terrain, zone segmentation, gate-blocked tiles, placed objects, player towns. It is
    never a count, an analysis, or anything else *derived from* the map at some point in
    the pipeline (see this package's AGENTS.md) -- that kind of data lives in the
    pipeline's ctx dict instead, and reaches a renderer/overlay through its own
    constructor, never through MapState.
    """

    size: int = 72
    # level -> 2-D list of tile-string objects (e.g. "gr2_")
    surfs: dict = field(default_factory=dict)
    # level -> 2-D list of tile-dict objects ({"t":…, "view":…, …})
    cells: dict = field(default_factory=dict)
    # level -> zone dict {zid: {tiles_set, terrain_type, area, centroid, …}}
    zones: dict = field(default_factory=dict)
    # level -> frozenset of blocked tiles from gates (BlockingOverlay)
    gate_blk: dict = field(default_factory=dict)
    # all placed objects across all levels
    objs: list = field(default_factory=list)
    # town objects in player order (VmapRenderer playability wiring)
    player_towns: list = field(default_factory=list)
