# core/placement/

Where an object stands and which tiles it takes. A module here reads `Footprint` and
`PlacedObject` values and returns tiles. It knows nothing about steps or the registry.

## Map

- `footprint.py`: footprint cell expansion: `anchored_cells`, `interactive_cells`, `decor_blocking_cells`, `overlay_clear` and `front_tiles`.
