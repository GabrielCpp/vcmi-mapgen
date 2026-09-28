# core/priors/

The corpus priors as frozen values the steps read. `corpus/` loads and saves them, and `corpus/mine/` mines them.

## Map

- `gates.py`: `GateStats`, the Subterranean Gate counts and spacing per map width.
- `gameplay.py`: `TerrainStats`, the gameplay statistics per terrain.
- `macro.py`: `MacroStats`, the corpus zone areas, terrain shares, terrain adjacency and barrier fractions.
- `markov.py`: `MarkovTables`, the terrain Markov chains that texture zone borders.
- `vegetation.py`: `VegetationStats`, the decoration statistics per terrain, and the pair
  potential and Cox field fits the vegetation sampler reads from them.
