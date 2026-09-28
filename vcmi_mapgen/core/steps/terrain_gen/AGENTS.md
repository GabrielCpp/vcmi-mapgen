# core/steps/terrain_gen/

## Map

- `macro_topo.py`: the macro terrain model: corpus zone areas and terrain mix, then the planned water mask, zones and corridors.
- `markov.py`: the terrain Markov chains learned from the corpus, which texture zone borders.
- `result.py`: `TerrainGrids` and `Segmentation`, which `TerrainStep` publishes.
- `step.py`: `TerrainStep`, which also segments each level into same-terrain zones.
