# models/ — data models, not logic

Every class here is a plain data container. Nothing in this folder computes, searches,
or derives anything — that logic lives in `steps/`, `kit/`, or `renderers/`. If you're
about to add a method here that does more than return/assemble already-known fields,
it belongs somewhere else.

## `MapState`

`MapState` is the render-only view of a finished map: exactly what `PngRenderer`,
`MapOverlay` and `VmapRenderer` read, and nothing else. A field belongs on `MapState`
**only if it describes the map itself, as VCMI means it** — terrain (`surfs`/`cells`),
zone segmentation (`zones`), gate-blocked tiles (`gate_blk`), placed objects (`objs`),
player towns (`player_towns`).

A field does **not** belong on `MapState` merely because a renderer wants to read it.
The test is: is this a fact the map itself carries, or is it an arbitrary, disposable
piece of analysis computed *from* the map at one point in the pipeline? Pocket geometry
is the concrete example that got this rule written down: which tiles form a sealed
nook, and at what depth, is something `steps.repair.caches.place_pocket_caches` computes
once, from the map's geometry, for its own purposes (guard placement, loot fill) — it is
not a property VCMI's own map format has any notion of. That kind of data goes into the
pipeline's `ctx` dict (see `pipeline.py`'s `Pipeline`), and whichever renderer/overlay
needs it receives it explicitly through its own constructor — never by reading it off
`MapState`, and never by recomputing it itself.

This is also why an overlay must never perform its own detection/search over the map:
`renderers/overlays/*.py` render data, they do not derive it. If an overlay needs
something that isn't a `MapState` fact, that something was already computed once by the
step that actually produces it — the overlay's constructor takes it as a parameter.
Recomputing it at render time from whatever objects happen to still be on the map is not
a rendering concern, and it drifts from the truth the moment a later step (a guard
dedup pass, a repair fixup) changes the object list in a way the original computation
never anticipated.
