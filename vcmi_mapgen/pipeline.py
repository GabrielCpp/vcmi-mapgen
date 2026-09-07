"""Map-generation primitives: the Gameplay/Vegetation/Pickup/Repair collaboration
workspaces, the PipelineStep contract, and the generic Pipeline engine that runs an
ordered list of steps against a shared ProviderRegistry. ``MapState`` itself lives in
``vcmi_mapgen.models`` (see that package's AGENTS.md) — it is a plain data model, not a
pipeline primitive.

A step owns its data as instance properties. Dependencies known when a pipeline is
assembled (seed, size, ...) go through the constructor. ``inject(ctx)`` is self-service:
a step pulls exactly the values it needs out of the shared ``ProviderRegistry``, typed by
their own dataclass, and stores them on itself. ``run(ontology, map_state)`` is passed the
shared ontology and the ``MapState`` being assembled on EVERY call, whether or not a given
step uses them.

**Every step must write onto `map_state`.** That is the step contract: a step exists to
advance the map, not to compute an intermediate value for the next step in line. Anything
else a step produces that a later step needs is published onto the SAME `ProviderRegistry`
it read from, as a typed dataclass (`ctx.provide(SomeResult(...))`) — never a raw
string-keyed dict entry, and there are no ctx-only steps: if a step's entire output would
otherwise be a `ProviderRegistry` value with nothing written to `map_state`, that is a
sign it is an artificial split of the step that actually needs it (merge them), not a
license to add a step whose only job is producing a context value. See
``vcmi_mapgen/steps/AGENTS.md`` for the full contract and worked examples, and
``vcmi_mapgen/models/AGENTS.md`` for exactly which data belongs on ``MapState`` and which
belongs in the registry.

``Pipeline`` replaces the old hand-wired ``PipelineBuilder``: composing a new step
sequence is just a different list of ``add_step()`` calls, never a new wiring method,
because a step declares what it needs by reading the registry itself instead of the
caller pushing named values sourced from specific upstream attributes. Step SEQUENCING
(the order `add_step()` calls are made in) is unchanged by any of this — steps still run
in the exact order they were added, for the same reason as always: MapState/workspace
mutation order and RNG determinism depend on it. The registry only changes how a value
crosses from one step to a later one; it does not turn the pipeline into a lazy
dependency graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.models import MapState

__all__ = ["MapState", "ZoneWorkspace", "LevelWorkspace", "PlacementWorkspace",
           "MissingProviderError", "ProviderRegistry", "PipelineStep", "Pipeline"]


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
    """Inter-step collaboration object for Gameplay/Vegetation/Pickup/Repair. Created by
    whichever of those four steps runs first (``ctx.get_or_create(PlacementWorkspace,
    PlacementWorkspace)``) and mutated in place by each of the other three in turn —
    ``MapState`` stays generic map-layer truth only, this is the one shared, progressively
    -built object every other cross-step value would need if it weren't a single
    computed-once value (see ``vcmi_mapgen/steps/AGENTS.md``)."""

    def __init__(self) -> None:
        self.levels: dict = {}   # level -> LevelWorkspace


class MissingProviderError(LookupError):
    """A step's inject() demanded a provider-backed value with no computed instance yet
    and no default given. This means the pipeline's steps were arranged incorrectly —
    one that produces it was omitted, or added out of order — not a recoverable
    condition: it is always raised, never worked around."""


class ProviderRegistry:
    """Type-keyed, memoized cross-step values — the ONLY channel for anything a step
    produces beyond its own ``MapState`` write (see ``pipeline.py``'s module docstring:
    no step may hold a raw string-keyed ctx entry, and there are no ctx-only steps).

    A producing step's ``run()`` calls ``provide(value)`` once it has computed its typed
    result. A later step's ``inject()`` calls ``require(SomeType)`` for a value some
    earlier step is guaranteed to have produced by then, or ``get(SomeType, default)``
    when the producing step might not have run at all (e.g. ``GateStep`` only runs for
    subterrain maps — its consumer reads an empty default instead).
    ``get_or_create(SomeType, factory)`` is for the one case where the FIRST demander
    creates the value and every later demander mutates that SAME instance further
    (``PlacementWorkspace``) — "the pipeline computes it for the first person who
    demands it, or returns the existing value."
    """

    def __init__(self) -> None:
        self._values: dict[type, object] = {}

    def provide(self, value) -> None:
        self._values[type(value)] = value

    def require(self, cls):
        if cls not in self._values:
            raise MissingProviderError(
                f"no {cls.__name__} has been provided yet — the step that produces it "
                f"is missing, or was added out of order")
        return self._values[cls]

    def get(self, cls, default=None):
        return self._values.get(cls, default)

    def get_or_create(self, cls, factory):
        if cls not in self._values:
            self._values[cls] = factory()
        return self._values[cls]


class PipelineStep:
    """Base class for all map-generation steps.

    Subclasses store constructor-known config as their own attributes (never a value
    another step produced). ``inject(ctx)`` is self-service: pull exactly the values this
    step needs out of the shared ``ProviderRegistry`` via ``ctx.require(SomeType)``/
    ``ctx.get(SomeType, default)``, storing them on self; the base implementation needs
    nothing and is a no-op. ``run(ontology, map_state)`` does the step's work — write onto
    ``map_state`` (every step must), and ``ctx.provide(...)`` anything a later step needs.
    ``ontology`` and ``map_state`` are ALWAYS passed, whether or not this particular step
    uses them.
    """

    def inject(self, ctx: ProviderRegistry) -> None:
        pass

    def run(self, ontology, map_state) -> None:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")


class Pipeline:
    """Runs an ordered list of PipelineStep instances against a shared ProviderRegistry.

    ``ontology`` (the real vcmi_mapgen.ontology module — the abstraction layer between
    game data and the pipeline) and ``map_state`` are known before any step runs, so
    every step's run() receives them directly. Everything else that flows from one step
    to a later one lives in ``ctx`` (a ``ProviderRegistry``), written directly by the
    producing step — Pipeline itself never inspects or merges a step's output; it only
    sequences inject()/run().

    ``run()`` returns only ``map_state``; anything else a caller needs is read
    afterward from ``pipeline.ctx`` by its dataclass type.
    """

    def __init__(self, ontology) -> None:
        self.ontology = ontology
        self.map_state = MapState()
        self.ctx = ProviderRegistry()
        self._steps: list[PipelineStep] = []

    def add_step(self, step: PipelineStep) -> "Pipeline":
        self._steps.append(step)
        return self

    def run(self) -> MapState:
        for step in self._steps:
            step.inject(self.ctx)
            step.run(self.ontology, self.map_state)
        return self.map_state
