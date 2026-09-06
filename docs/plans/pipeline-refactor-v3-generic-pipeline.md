# Pipeline Refactor Plan v3 — generic Pipeline, no hand-wired builder

Builds on `pipeline-refactor-v2-folders.md` (v2), which reshaped `steps/` into
folder-per-step and introduced `PlacementWorkspace`/`LevelWorkspace`/`ZoneWorkspace` as the
inter-step collaboration channel. Some time after v2 landed, a `PipelineBuilder` class
(`pipeline_builder.py`, undocumented by any plan) was introduced on top of that: each
subcommand family got its own hand-written method (`run_generate`, `run_identity_rebuild`,
`run_deform_rebuild`) that constructs each step in order, reads back whichever of its
properties a later step needs, and calls that step's `inject(**named_kwargs)`.

That works, but it means the wiring between steps only exists pre-written for the exact
sequences those three methods encode. Skipping, reordering, or adding a step means
hand-writing a new method — the wiring is not composable. This plan replaces
`PipelineBuilder` with a generic `Pipeline` that holds an ordered list of steps and a shared
context dict; a step pulls what it needs from that dict itself, so composing a new sequence
is just a different list of `add_step()` calls, never a new wiring method.

v1 and v2 stay as the historical record of how `pipeline.py`/`steps/` reached their current
shape. This document is the one to follow going forward.

---

## Goals

1. Replace `PipelineBuilder.run_generate` / `run_identity_rebuild` / `run_deform_rebuild`
   with one generic `Pipeline` class (`pipeline.py`), used by both the `generate` family and
   the identity-rebuild/deform family.
2. Change the `PipelineStep` contract so a step *pulls* what it needs from a shared context
   dict (self-service), instead of the builder *pushing* named kwargs sourced from specific
   upstream attributes. Adding, reordering, or omitting a step never requires writing new
   wiring — only changing which `add_step()` calls happen.
3. Make `ontology` (an `Ontology` instance — a thin facade class in `ontology.py`, wrapping
   this module's own accessor functions one-for-one, so the pipeline holds and passes a
   single object instead of the bare module — the abstraction layer between game data and
   the pipeline) and `map_state` (the `MapState` being built up) uniformly available to
   every step's `run()`, whether or not a given step uses them.
4. Fix the one confirmed place a step currently bypasses the ontology and hardcodes an
   object's identity: `steps/gameplay/water.py`'s seaport/shipyard placement
   (`_SEAPORT_ANIM`, a hardcoded mask) — every other placed object in that file already goes
   through an `ON.identity_of`/`gameplay_pool` lookup.
5. Delete `pipeline_builder.py` entirely. `cli.py` builds a `Pipeline` directly per
   subcommand.
6. Leave `extract`/`inspect`/`features`/`render-ontology` untouched — they never went
   through `PipelineBuilder` (they call `rebuild.engine`/`rebuild.render` functions
   directly) and are out of scope here.

---

## The new `PipelineStep` contract

Replaces "constructor (compile-time config) + `inject(**named_kwargs)` (upstream values,
pushed) + parameterless `run()`" with:

```python
class MissingContextKeyError(LookupError):
    """A step's inject() needed a ctx key that isn't there yet, or the value under it
    isn't the type the step expected -- an incorrect arrangement of steps in the
    pipeline (a step was omitted, or added out of order), not a recoverable condition."""


class PipelineStep:
    """Constructor: compile-time-known config only (seed, size, subterrain, ...) --
    never a value another step produced.

    inject(ctx): self-service. Pull exactly the keys this step needs out of the shared
    ctx dict, isinstance-check each one (a specific dataclass type counts), store on
    self. Raise MissingContextKeyError -- do not silently default -- when a key is
    absent or the wrong type: that means the steps were arranged incorrectly.

    run(ontology, map_state): no longer parameterless. `ontology`
    (vcmi_mapgen.ontology, the real abstraction layer for object identity/mask/terrain
    data) and `map_state` (the MapState being assembled) are passed to EVERY step's
    run(), whether or not that particular step uses them. A step that produces a
    MapState field (surfs/cells/zones/gate_blk/objs/player_towns) writes it directly
    onto map_state; a step that produces anything else another step or the caller
    needs writes it directly into the ctx dict it captured during inject()."""

    def inject(self, ctx: dict) -> None:
        pass  # a step that needs nothing from ctx doesn't override this

    def run(self, ontology, map_state) -> None:
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")
```

A small helper on the base class avoids repeating the same pull-and-check dance in every
step's `inject()`:

```python
    def _require(self, ctx: dict, key: str, expected_type) -> object:
        if key not in ctx:
            raise MissingContextKeyError(f"{type(self).__name__}.inject(): "
                                          f"ctx has no {key!r}")
        value = ctx[key]
        if not isinstance(value, expected_type):
            raise MissingContextKeyError(
                f"{type(self).__name__}.inject(): ctx[{key!r}] is "
                f"{type(value).__name__}, expected {expected_type.__name__}")
        return value
```

## `Pipeline`

```python
class Pipeline:
    """ontology and map_state are the two things every step's run() always receives,
    known before any step runs. ctx is everything else -- produced by one step,
    consumed by a later one -- written directly by the producing step, never merged
    in by Pipeline itself."""

    def __init__(self, ontology):
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
```

`run()` returns **only** `map_state`. Anything else a caller needs (`log`, `player_zids`,
`template`, `fm`, `stats`, `document`, `verify`, ...) is read afterward from `pipeline.ctx`.
No stop-point concept lives here at all — a caller that wants to stop early (`generate
--stop-after`) simply calls `add_step()` for fewer steps; `Pipeline` has no idea a "stop
point" concept exists.

---

## Who writes what, where

**`MapState` fields — written directly by the producing step, never through `ctx`:**

| Field | Written by |
|---|---|
| `surfs`, `cells` | `TileStep` |
| `zones` | `SegmentStep` |
| `gate_blk` | `GateStep` (only when present) |
| `objs` | `GameplayStep` (sets), then `VegetationStep`/`PickupStep`/`RepairStep` (each reads the current value and writes back the updated one) |
| `player_towns` | `GameplayStep` |

**`ctx` keys — written directly by the producing step, read by later steps or the caller:**

| Key | Written by | Read by |
|---|---|---|
| `workspace` (the folded-in `PlacementWorkspace`) | `GameplayStep` (created once, first step to need it) | `VegetationStep`, `PickupStep`, `RepairStep` |
| `zone_records`, `targets` | `PickupStep` | `RepairStep` |
| `player_zids` | `GameplayStep` | `RepairStep`, the caller (CLI reporting) |
| `log` | `RepairStep` | the caller (CLI printing) |
| `template` | `ExtractTemplateStep` | `RebuildMapStep`, `DeformWarpStep` |
| `fm` | `RebuildMapStep` / `DeformWarpStep` | `VerifyStep`, `FmDocumentStep` |
| `stats` | `RebuildMapStep` | the caller |
| `document` | `FmDocumentStep` | the caller |
| `verify` | `VerifyStep` | the caller |

`tunnel_protect` (from `TerrainGenStep`) and the four `gate_*` values (from `GateStep`, only
when subterrain) follow the same rule — written to `ctx` once, read by whichever later steps
need them, no special-casing.

---

## The seaport/ontology fix (`steps/gameplay/water.py`)

Today: `_SEAPORT_ANIM = "avxshyd0"` and a hardcoded mask, assembled directly into the
placed object's `type`/`subtype`/`animation`/`mask` — the one identity in this file that
skips the `ON.identity_of`/`gameplay_pool` lookup every other object there uses.

Fix: `GameplayStep.run(ontology, map_state)` threads `ontology` into the specific
`water.py` call that places the seaport (not a blanket rewrite of every helper function —
only the one that currently violates the rule), and that call resolves the identity via
`ontology.identity_of(...)` / `ontology.gameplay_pool(terrain, "WATER_TRANSPORT")` the same
way the rest of the file already does, dropping `_SEAPORT_ANIM`/`_SEAPORT_MASK`.

---

## Migration order (each phase independently committable and verifiable)

### Phase 1 — `pipeline.py`: new contract, no step migrated yet

Add `MissingContextKeyError`, rewrite `PipelineStep` to the new contract (`inject(ctx)`,
`run(ontology, map_state)`, the `_require` helper), add the `Pipeline` class. `MapState`,
`ZoneWorkspace`, `LevelWorkspace`, `PlacementWorkspace` are unchanged. Nothing else in the
tree is touched yet, so nothing breaks or is expected to pass differently.

### Phase 2 — Migrate each step, one at a time

For each of the 13 step files (`terrain_gen`, `tile`, `segment`, `gate`, `gameplay`,
`vegetation`, `pickup`, `repair`, `extract_template`, `rebuild_map`, `verify`,
`fm_document`, `deform_warp`): change `inject(self, **named_kwargs)` to
`inject(self, ctx)` using `self._require(ctx, key, type)` for each value the step needs
(replacing the named-kwarg manifest with the same information as `_require` calls); change
`run(self)` to `run(self, ontology, map_state)`, moving whichever `state.foo = ...` lines
used to live in the builder into the step itself. `GameplayStep`/`VegetationStep`/
`PickupStep`/`RepairStep` also lose their `workspace=` constructor param — they instead
create-or-fetch `ctx["workspace"]` in `inject()`.

Verify each step in isolation (its own `*_test.py`) before moving to the next; a step
earlier in the sequence stabilizes before a later one is touched.

### Phase 3 — Seaport/ontology fix

Thread `ontology` from `GameplayStep.run()` into `water.py`'s seaport-placing call; replace
`_SEAPORT_ANIM`/`_SEAPORT_MASK` with an ontology lookup. Verify: a generated map's seaport
objects still resolve to a legal `shipyard` identity (same visible behavior, different
provenance).

### Phase 4 — `cli.py` rewire, `pipeline_builder.py` deletion

Replace every `PipelineBuilder().run_generate(...)` / `run_identity_rebuild(...)` /
`run_deform_rebuild(...)` call site with an explicit `Pipeline(ontology)` +
sequence of `add_step(...)` + `pipeline.run()`, reading anything beyond `map_state` from
`pipeline.ctx[...]`. `--stop-after` becomes "add fewer steps" in `cmd_generate`. Delete
`pipeline_builder.py` (including `GenerateResult`/`IdentityRebuildResult` — `cli.py` reads
`pipeline.ctx` directly instead of a wrapper dataclass).

### Phase 5 — Update the two dependent tests

`steps/pickup/step_test.py` and `steps/gameplay/step_test.py` each build a fixture via
`PipelineBuilder().run_generate(..., stop_after="pickup")`. Replace with the equivalent
`Pipeline` + `add_step()` sequence, truncated the same way.

---

## Contracts that must not break

| Contract | How to verify |
|---|---|
| Identity guarantee | `uv run python -m vcmi_mapgen.cli rebuild "All for One" --identity --verify` prints `IDENTITY OK` |
| Full test suite | `uv run pytest` green (same pre-existing unrelated failure aside) |
| `generate` still produces a playable map | `uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72` completes, PNG + vmap written |
| Determinism | Same seed -> same output before and after the refactor |
| `--stop-after` still works | `uv run python -m vcmi_mapgen.cli generate --stop-after segment ...` returns a partial `MapState` with only `surfs`/`cells`/`zones` populated |

---

## Open implementation-time judgment calls (deliberately not pinned down further)

- Exact wording/fields of `MissingContextKeyError` beyond "step name + key name" —
  whichever is clearest when it actually fires.
- Whether `ctx["workspace"]` is created eagerly by `Pipeline.__init__` or lazily by
  whichever step first needs it (`GameplayStep`) — either is fine since nothing reads it
  before `GameplayStep` runs.
- Whether `add_step` returning `self` (chaining) is used anywhere in practice, or `cli.py`
  just calls it as separate statements — purely a style choice at the call site.
