"""Map-generation/rebuild primitives: the render-only MapState, the Gameplay/Vegetation/
Pickup/Repair collaboration workspaces, and the PipelineStep base contract.

A step owns its data as instance properties. Dependencies known when a pipeline is
assembled (seed, size, ...) go through the constructor; values produced by an earlier
step are delivered through ``inject()``, whose keyword parameters ARE the step's
declared manifest of what it needs. ``run()`` takes nothing. A ``PipelineBuilder``
(see ``pipeline_builder.py``) wires steps together by hand: run a step, read back
whichever of its properties a later step needs, call that step's ``inject()``, run it.

``MapState`` is assembled by the builder, once a run finishes, purely for the render
phase (``PngRenderer`` / ``MapOverlay`` / ``VmapRenderer``) — no step holds or mutates
one, so adding a step never touches this schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MapState:
    """The narrow, render-only view of a finished map: exactly what PngRenderer,
    MapOverlay and VmapRenderer read, and nothing else."""

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


@dataclass
class ZoneWorkspace:
    """One zone's handoff data, mutated in place as Gameplay -> Vegetation -> Pickup ->
    Repair each run. Not a MapState field: this is step-collaboration bookkeeping, not a
    map-level fact anything outside these four steps needs to read."""

    terrain: str = ""
    ts: frozenset = frozenset()          # set by GameplayStep
    ts_full: frozenset = frozenset()
    gobjs: list = field(default_factory=list)
    occupied: frozenset = frozenset()
    gblocked: frozenset = frozenset()
    approaches: tuple = ()
    entrances: list = field(default_factory=list)   # kit.topology.plan_entrances entries
    prot: frozenset = frozenset()         # protected web
    rim8: frozenset = frozenset()
    ent_bands: frozenset = frozenset()
    blocked: frozenset = frozenset()      # set by VegetationStep
    open_set: frozenset = frozenset()
    passable: frozenset = frozenset()
    reach: frozenset = frozenset()        # set by PickupStep
    used: frozenset = frozenset()


@dataclass
class LevelWorkspace:
    zones: dict = field(default_factory=dict)          # zid -> ZoneWorkspace
    entrance_plan: dict = field(default_factory=dict)
    ridge: frozenset = frozenset()
    seal_avoid: set = field(default_factory=set)
    hard_avoid: set = field(default_factory=set)
    guard_tiles: frozenset = frozenset()
    # seaport blocking/approach cells (set by GameplayStep) — vegetation must forbid them
    seaport_blk: frozenset = frozenset()
    seaport_appr: frozenset = frozenset()
    water_tiles: frozenset = frozenset()   # set by GameplayStep — needed by place_loot_zones
    town_of_zone: dict = field(default_factory=dict)   # set by GameplayStep — zid -> town obj


class PlacementWorkspace:
    """Inter-step collaboration object for Gameplay/Vegetation/Pickup/Repair. Shared by
    reference, injected via constructor — not threaded through ``MapState`` and not a
    raw dict. ``MapState`` stays generic map-layer truth only."""

    def __init__(self) -> None:
        self.levels: dict = {}   # level -> LevelWorkspace


class PipelineStep:
    """Base class for all map-generation/rebuild steps.

    Subclasses store constructor-known config as their own attributes, override
    ``inject()`` to accept named, typed values produced by earlier steps (the
    parameter names are the step's declared manifest), and implement ``run()`` to
    compute their own output properties from those two sources.
    """

    def inject(self, **kwargs) -> None:
        """Accept values produced by earlier steps. The base implementation accepts
        none; a step that needs upstream values overrides this with named, typed
        keyword parameters."""
        if kwargs:
            raise TypeError(
                f"{type(self).__name__} does not accept injected values: {sorted(kwargs)}"
            )

    def run(self) -> None:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")
