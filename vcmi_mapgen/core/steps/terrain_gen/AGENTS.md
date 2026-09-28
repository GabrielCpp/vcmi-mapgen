# core/steps/terrain_gen/

## Map

- `despeckle.py`: merges terrain patches too small or too thin for the tile art into the land around them.
- `gate_sites.py`: the Subterranean Gate sites, carved open on both levels and tunnelled to the nearest cavern.
- `macro.py`: the macro terrain model: the planned water mask, zones and corridors, drawn from `MacroStats`.
- `result.py`: `TerrainGrids`, the tunnel cells, and `Segmentation`, which `TerrainStep` publishes.
- `step.py`: `TerrainStep`, which also segments each level into same-terrain zones.
- `texture.py`: the boundary texturing, which samples the corpus Markov tables in a band around zone borders.
