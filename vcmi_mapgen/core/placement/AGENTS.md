# core/placement/

Where an object stands and which tiles it takes. A module here reads `Footprint` and
`PlacedObject` values and returns tiles or placed objects. It knows nothing about steps or the registry.

## Map

- `footprint.py`: footprint cell expansion: `anchored_cells`, `footprint_cells`, `blocking_cells`, `interactive_cells`, `decor_blocking_cells`, `overlay_clear` and `front_tiles`.
- `guards.py`: the GAP rule, the gameplay-footprint fit, a guard's zone of control and spacing, and the random-monster identity.
- `cells.py`: `CellRules` and `legal_cells`, the tiles a pickup may stand on.
- `identity.py`: the random class ids and the identity picks. `pick_kind` draws one fixed identity from a pool under a caller's weight, and `solo_visit_pool` lists the visitable kinds a lone pickup may be.
- `intensity.py`: the per-tile placement intensity over edge depth, gate distance and openness, and the stochastic rounding of a density into a count.
- `place.py`: `PlaceTarget`, `PlaceSpec` and `place_one`, the guarded placement over the open field, plus reachability.
- `rewards.py`: the one reward builder, which draws the pandoraBox reward and the
  seer-hut quest payout a tier apart.
- `site.py`: where an object may stand in a zone: the shared level field, the cover index and each zone's spot search, from the `SiteZone` a zone brings to the `PlacedZone` it leaves.
- `scatter.py`: `place_scatter`, the unguarded resource piles over the finished open field. A
  `ScatterZone` carries its gate bands, so scatter never reads a label grid.
- `water.py`: the water-body objects and the seaport guarantee, drawn by the zone plan and
  committed first by the gameplay step.
