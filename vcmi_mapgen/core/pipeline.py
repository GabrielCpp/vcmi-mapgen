"""Map-generation primitives: the PipelineStep contract, and the generic Pipeline engine that
runs an ordered list of steps against a shared ProviderRegistry. ``MapState`` itself lives in
``vcmi_mapgen.core.model`` (see that package's AGENTS.md) — it is a plain data model, not a
pipeline primitive.

A step owns its data as instance properties. Dependencies known when a pipeline is
assembled (seed, size, ...) go through the constructor. ``inject(ctx)`` is self-service:
a step pulls exactly the values it needs out of the shared ``ProviderRegistry``, typed by
their own dataclass, and stores them on itself. ``run(catalog, map_state)`` is passed the
shared ``Catalog`` and the ``MapState`` being assembled on EVERY call, whether or not a given
step uses them.

**Every step must write onto `map_state`.** That is the step contract: a step exists to
advance the map, not to compute an intermediate value for the next step in line. Anything
else a step produces that a later step needs is published onto the SAME `ProviderRegistry`
it read from, as a typed dataclass (`ctx.provide(SomeResult(...))`) — never a raw
string-keyed dict entry, and there are no ctx-only steps: if a step's entire output would
otherwise be a `ProviderRegistry` value with nothing written to `map_state`, that is a
sign it is an artificial split of the step that actually needs it (merge them), not a
license to add a step whose only job is producing a context value. See
``vcmi_mapgen/core/steps/AGENTS.md`` for the full contract and worked examples, and
``vcmi_mapgen/core/model/AGENTS.md`` for exactly which data belongs on ``MapState`` and which
belongs in the registry.

``Pipeline`` replaces the old hand-wired ``PipelineBuilder``: composing a new step
sequence is just a different list of ``add_step()`` calls, never a new wiring method,
because a step declares what it needs by reading the registry itself instead of the
caller pushing named values sourced from specific upstream attributes. Step SEQUENCING
(the order `add_step()` calls are made in) is unchanged by any of this — steps still run
in the exact order they were added, for the same reason as always: MapState
mutation order and RNG determinism depend on it. The registry only changes how a value
crosses from one step to a later one; it does not turn the pipeline into a lazy
dependency graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import cast, overload

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState

__all__ = [
    "MapState",
    "MissingProviderError",
    "Pipeline",
    "PipelineStep",
    "ProviderRegistry",
]


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
    when the producing step might not have run at all (e.g. the CLI reads an empty
    ``PortalResult`` default when a run stops before ``PortalStep``). Each value is provided
    once, by the one step that produces it.
    """

    def __init__(self) -> None:
        self._values: dict[type, object] = {}

    def provide(self, value: object) -> None:
        self._values[type(value)] = value

    def require[T](self, cls: type[T]) -> T:
        if cls not in self._values:
            raise MissingProviderError(
                f"no {cls.__name__} has been provided yet — the step that produces it "
                + "is missing, or was added out of order"
            )
        return cast(T, self._values[cls])

    @overload
    def get[T](self, cls: type[T]) -> T | None: ...

    @overload
    def get[T](self, cls: type[T], default: T) -> T: ...

    def get[T](self, cls: type[T], default: T | None = None) -> T | None:
        return cast(T | None, self._values.get(cls, default))


class PipelineStep(ABC):
    """Base class for all map-generation steps.

    Subclasses store constructor-known config as their own attributes (never a value
    another step produced). ``inject(ctx)`` is self-service: pull exactly the values this
    step needs out of the shared ``ProviderRegistry`` via ``ctx.require(SomeType)``/
    ``ctx.get(SomeType, default)``, storing them on self; the base implementation needs
    nothing and is a no-op. ``run(catalog, map_state)`` does the step's work — write onto
    ``map_state`` (every step must), and ``ctx.provide(...)`` anything a later step needs.
    ``catalog`` and ``map_state`` are ALWAYS passed, whether or not this particular step
    uses them.
    """

    def inject(self, ctx: ProviderRegistry) -> None:
        _ = ctx

    @abstractmethod
    def run(self, catalog: Catalog, map_state: MapState) -> None:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")


class Pipeline:
    """Runs an ordered list of PipelineStep instances against a shared ProviderRegistry.

    ``catalog`` (the ``Catalog`` port, the only way a step learns about objects) and
    ``map_state`` are known before any step runs, so
    every step's run() receives them directly. Everything else that flows from one step
    to a later one lives in ``ctx`` (a ``ProviderRegistry``), written directly by the
    producing step — Pipeline itself never inspects or merges a step's output; it only
    sequences inject()/run().

    ``run()`` returns only ``map_state``; anything else a caller needs is read
    afterward from ``pipeline.ctx`` by its dataclass type.
    """

    def __init__(self, catalog: Catalog, size: int) -> None:
        self.catalog: Catalog = catalog
        self.map_state: MapState = MapState(size=size)
        self.ctx: ProviderRegistry = ProviderRegistry()
        self._steps: list[PipelineStep] = []

    def add_step(self, step: PipelineStep) -> Pipeline:
        self._steps.append(step)
        return self

    def run(self) -> MapState:
        for step in self._steps:
            step.inject(self.ctx)
            step.run(self.catalog, self.map_state)
        return self.map_state
