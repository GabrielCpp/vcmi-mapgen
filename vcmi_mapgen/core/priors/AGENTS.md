# core/priors/

The corpus priors as frozen values the steps read. `corpus/` loads and saves them, and `corpus/mine/` mines them.

## Map

- `bundle.py`: `Priors`, every prior one generation run reads, and `TerrainPriors`, one
  level's macro statistics and Markov tables.
- `gates.py`: `GateStats`, the Subterranean Gate counts and spacing per map width.
- `gameplay.py`: `TerrainStats`, the gameplay statistics per terrain, and `GameplayStats`,
  one level's statistics keyed by terrain.
- `macro.py`: `MacroStats`, the corpus zone areas, terrain shares, terrain adjacency and barrier fractions.
- `pocket_masks.py`: `PocketMask`, one drawn pocket shape in one orientation, as offsets from its guard.
- `markov.py`: `MarkovTables`, the terrain Markov chains that texture zone borders.
- `vegetation.py`: `VegetationStats`, the decoration statistics per terrain, and the pair
  potential and Cox field fits the vegetation sampler reads from them.
