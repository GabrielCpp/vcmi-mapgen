# core/steps/terrain_gen/

## Map

- `macro_topo.py`: the macro terrain model: corpus zone areas and terrain mix, then the planned water mask, zones and corridors.
- `markov.py`: the terrain Markov chains learned from the corpus, which texture zone borders.
- `step.py`: `TerrainStep` and the `TerrainGrids` it publishes.
