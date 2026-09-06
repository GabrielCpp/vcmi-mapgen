"""Map-generation/rebuild primitives: the Gameplay/Vegetation/Pickup/Repair collaboration
workspaces, the PipelineStep contract, and the generic Pipeline engine that runs an
ordered list of steps against a shared context. ``MapState`` itself lives in
``vcmi_mapgen.models`` (see that package's AGENTS.md) — it is a plain data model, not a
pipeline primitive.

A step owns its data as instance properties. Dependencies known when a pipeline is
assembled (seed, size, ...) go through the constructor. ``inject(ctx)`` is self-service:
a step pulls exactly the keys it needs out of the shared context dict, type-checks each
one, and stores them on itself — raising ``MissingContextKeyError`` when a key is absent
or the wrong type, since that means the steps were arranged incorrectly (one was
omitted, or added out of order). ``run(ontology, map_state)`` is passed the shared
ontology and the ``MapState`` being assembled on EVERY call, whether or not a given step
uses them; a step that produces a ``MapState`` field writes it there directly, and a
step that produces anything else a later step (or a renderer) needs writes it directly
into the same context dict it read from — never onto ``MapState``, and never a separate
merge step. See ``vcmi_mapgen/models/AGENTS.md`` for exactly which data belongs on
``MapState`` and which belongs in ``ctx``.

``Pipeline`` (see below) replaces the old hand-wired ``PipelineBuilder``: composing a
new step sequence is just a different list of ``add_step()`` calls, never a new wiring
method, because a step declares what it needs by reading the context itself instead of
the caller pushing named values sourced from specific upstream attributes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.models import MapState

__all__ = ["MapState", "ZoneWorkspace", "LevelWorkspace", "PlacementWorkspace",
           "MissingContextKeyError", "PipelineStep", "Pipeline"]


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


class MissingContextKeyError(LookupError):
    """A step's inject() needed a context key that isn't there yet, or the value under
    it isn't the type the step expected. This means the pipeline's steps were arranged
    incorrectly — one was omitted, or added out of order — not a recoverable condition:
    it is always raised, never worked around."""


class PipelineStep:
    """Base class for all map-generation/rebuild steps.

    Subclasses store constructor-known config as their own attributes (never a value
    another step produced). ``inject(ctx)`` is self-service: pull exactly the keys this
    step needs out of the shared context dict via ``self._require(ctx, key, type)``,
    storing them on self; the base implementation needs nothing and is a no-op.
    ``run(ontology, map_state)`` does the step's work — ``ontology`` and ``map_state``
    are ALWAYS passed, whether or not this particular step uses them.
    """

    def inject(self, ctx: dict) -> None:
        pass

    def run(self, ontology, map_state) -> None:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")

    def _require(self, ctx: dict, key: str, expected_type):
        """Fetch ``ctx[key]``, raising MissingContextKeyError if it's absent or not an
        instance of ``expected_type`` (a class, or a tuple of classes)."""
        if key not in ctx:
            raise MissingContextKeyError(
                f"{type(self).__name__}.inject(): ctx has no {key!r}")
        value = ctx[key]
        if not isinstance(value, expected_type):
            type_name = getattr(expected_type, "__name__", expected_type)
            raise MissingContextKeyError(
                f"{type(self).__name__}.inject(): ctx[{key!r}] is "
                f"{type(value).__name__}, expected {type_name}")
        return value


class Pipeline:
    """Runs an ordered list of PipelineStep instances against a shared context dict.

    ``ontology`` (the real vcmi_mapgen.ontology module — the abstraction layer between
    game data and the pipeline) and ``map_state`` are known before any step runs, so
    every step's run() receives them directly. Everything else that flows from one step
    to a later one lives in ``ctx``, written directly by the producing step — Pipeline
    itself never inspects or merges a step's output; it only sequences inject()/run().

    ``run()`` returns only ``map_state``; anything else a caller needs (log,
    player_zids, template, fm, stats, document, verify, ...) is read afterward from
    ``pipeline.ctx``.
    """

    def __init__(self, ontology) -> None:
        self.ontology = ontology
        self.map_state = MapState()
        self.ctx: dict = {}
        self._steps: list[PipelineStep] = []

    def add_step(self, step: PipelineStep) -> "Pipeline":
        self._steps.append(step)
        return self

    def run(self) -> MapState:
        for step in self._steps:
            step.inject(self.ctx)
            step.run(self.ontology, self.map_state)
        return self.map_state
