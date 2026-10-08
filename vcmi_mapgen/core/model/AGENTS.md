# core/model/ — data models, not logic

Every class here is a plain data container. Nothing in this folder computes, searches,
or derives anything — that logic lives in `core/steps/`, `core/placement/`, `core/grid/`, or `renderers/`. If you're
about to add a method here that does more than return/assemble already-known fields,
it belongs somewhere else.

The one exception is `MapState`, which is the map's grid API: `MapState(size=...)`,
`at(level, x, y)` (a `TileView` with terrain, zone, covering objects and their roles, or
the blocking `BORDER` sentinel outside the map), `taken_tiles(level)`, `conflicts(obj)`,
`place` and `add_objs`. Those methods answer questions about tiles and objects that are
already on the map. They never search or score. Every placement step writes its objects
through `add_objs(new)`, which refuses an object that covers another object's
visit, entrance or approach tile. The catalog seals a lasting object's visit tile into an
entrance (`Catalog.is_vanish` is false), so that tile blocks and the tile below it is its
approach. A guard may stand on an approach tile, and any overlay
may sit over a resource pile or reward pickup. A placer never relies on that refusal. It
asks a `CoverIndex` before each placement and skips the spot. A `CoverIndex` built with
`rules` also asks each `PlacementRule` in turn. `StartRoomRule` is the one rule today: it
keeps guards and walls off a player town's start. The same `CoverIndex` owns the
cells placements have claimed: `claim(cells)` adds them, `mark()` records a point, and
`rollback(mark)` forgets every object and claim since that point.

## Map

- `map_state.py`: `MapState`, the tile grid and the objects on it, and the grid API.
- `objects.py`: the object and zone records: `PlacedObject`, its `Identity` and `Entrance` and `Zone`, and the `Footprint` an object covers, a set of cells each with its `Role`. A placed object carries its `kind` and its payload, never an engine type or engine options.
- `payload.py`: `Payload`, what a placed object holds for the game: a `Guard`, a `Reward`, a seer hut's `Quest`, a `Scroll`'s spell, a `Town` or a `Dwelling` tied to its town.
- `terrain.py`: `Terrain`, the terrain vocabulary, and which terrains are water, barrier or land.
- `artifact.py`: `ArtifactTier`, the four artifact classes a map's treasure draws from, and `ArtifactSet`, a combined artifact with its parts.
- `purpose.py`: `Purpose`, the purposes objects are placed for, and the groups `VISIT_PURPOSES` and `COUNTED`.
- `resource.py`: `Resource`, the resources a map's economy counts.
- `road.py`: `Road`, the three road surfaces a tile can carry, by VCMI road index.

## `MapState`

`MapState` is the render-only view of a finished map: exactly what `PngRenderer`,
`MapOverlay` and `VmapRenderer` read, and nothing else. A field belongs on `MapState`
**only if it describes the map itself, as VCMI means it** — terrain (`terrain`, one `Terrain` per tile),
roads (`roads`, one `Road` per road tile by level), gate-blocked tiles (`gate_blk`), placed objects (`objs`), player towns (`player_towns`).

Zone segmentation is not a map fact. The map is a grid, and a `.vmap` has no notion of
zones. `TerrainStep` computes them from the terrain, so they are analysis. They live in
the registry as `Segmentation`, which each consumer requires. Overlays that draw zones
take them through their constructor.

A field does **not** belong on `MapState` merely because a renderer wants to read it.
The test is: is this a fact the map itself carries, or is it an arbitrary, disposable
piece of analysis computed *from* the map at one point in the pipeline? Pocket geometry
is the concrete example that got this rule written down: which tiles form a sealed
nook, and at what depth, is something `core.steps.loot.pickups.place_pocket_caches` computes
once, from the map's geometry, for its own purposes (guard placement, loot fill) — it is
not a property VCMI's own map format has any notion of. That kind of data goes into the
pipeline's `ProviderRegistry` as a typed dataclass (`LootStep` provides `LootResult`), and
whichever renderer/overlay needs it receives it explicitly through its own constructor —
never by reading it off `MapState`, and never by recomputing it itself.

This is also why an overlay must never perform its own detection/search over the map:
`renderers/overlays/*.py` render data, they do not derive it. If an overlay needs
something that isn't a `MapState` fact, that something was already computed once by the
step that actually produces it — the overlay's constructor takes it as a parameter.
Recomputing it at render time from whatever objects happen to still be on the map is not
a rendering concern, and it drifts from the truth the moment a later step adds objects
the original computation never anticipated.
