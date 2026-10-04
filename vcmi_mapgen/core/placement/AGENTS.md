# core/placement/

Where an object stands and which tiles it takes. A module here reads `Footprint` and
`PlacedObject` values and returns tiles or placed objects. It knows nothing about steps or the registry.

## Map

- `footprint.py`: footprint cell expansion: `anchored_cells`, `footprint_cells`, `blocking_cells`, `interactive_cells`, `decor_blocking_cells`, `overlay_clear`, `overlay_cells` and `front_tiles`. `overlay_cells` lists the cells of a sprite that neither block nor interact.
- `ground.py`: the ground rule, map-math C5. `stands` holds when every solid cell of an identity sits on a tile whose terrain the catalog allows. Vegetation, the mine seals and the gameplay spot search all call it, because a place's accents and transitions put foreign terrain inside a zone.
- `guards.py`: the GAP rule, the gameplay-footprint fit, a guard's zone of control and spacing, and the random-monster identity.
- `cells.py`: `CellRules` and `legal_cells`, the tiles a pickup may stand on.
- `identity.py`: the random class ids and the identity picks. `pick_kind` draws one fixed identity from a pool under a caller's weight, and `solo_visit_pool` lists the visitable kinds a lone pickup may be.
- `intensity.py`: the per-tile placement intensity over edge depth, gate distance and openness, and the stochastic rounding of a density into a count.
- `place.py`: `PlaceTarget`, `PlaceSpec` and `place_one`, the guarded placement over the open field, plus reachability.
- `rewards.py`: the one reward builder, which draws the pandoraBox reward and the
  seer-hut quest payout a tier apart.
- `site.py`: where an object may stand in a zone: the shared level field, the cover index and each zone's spot search with its `Footing` per purpose, from the `SiteZone` a zone brings to the `PlacedZone` it leaves. `ZoneSite.place` takes an optional `Footing` that overrides the purpose's own. `HOME_FOOTING` is the town footing of a planned home: its sprite overlay may reach past the zone anywhere on the map, while its body still keeps to the zone or to vegetation.
- `start_room.py`: `StartRoomRule`, the placement rule that keeps a guard's zone of control off a player town's entrance and stops any solid object from walling in its start. `start_rules` builds it for a finished map's level.
- `scatter.py`: `place_scatter`, the unguarded resource piles over the finished open field. A
  `ScatterZone` carries its gate bands, so scatter never reads a label grid.
- `water.py`: the water-body objects and the seaport guarantee, drawn by the zone plan and
  committed first by the gameplay step.
