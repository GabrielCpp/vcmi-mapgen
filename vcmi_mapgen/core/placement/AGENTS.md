# core/placement/

Where an object stands and which tiles it takes. A module here reads `Footprint` and
`PlacedObject` values and returns tiles or placed objects. It knows nothing about steps or the registry.

## Map

- `footprint.py`: footprint cell expansion: `anchored_cells`, `footprint_cells`, `blocking_cells`, `interactive_cells`, `decor_blocking_cells`, `overlay_clear` and `front_tiles`.
- `rules.py`: `TerrainGate`, the terrain placement rule `MapState.add_objs` checks.
- `guards.py`: the GAP rule, the gameplay-footprint fit, a guard's zone of control and spacing, and the random-monster identity.
- `cells.py`: `CellRules` and `legal_cells`, the tiles a pickup may stand on.
- `identity.py`: the identity picks for a pickup, random classes first, then a fixed identity weighted by the corpus mix.
- `intensity.py`: the per-tile placement intensity over edge depth, gate distance and openness.
- `place.py`: `PlaceTarget`, `PlaceSpec` and `place_one`, the guarded placement over the open field, plus reachability.
- `rewards.py`: the pandoraBox rewards.
- `site.py`: where an object may stand in a zone: the shared level field, the cover index and each zone's spot search.
- `scatter.py`: `place_scatter`, the unguarded resource piles over the finished open field.
