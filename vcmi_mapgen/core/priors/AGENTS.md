# core/priors/

The corpus priors as frozen values the steps read. `corpus/` loads and saves them, and `corpus/mine/` mines them.

## Map

- `gates.py`: `GateStats`, the Subterranean Gate counts and spacing per map width, and `GATE_ANIM`.
- `gameplay.py`: `TerrainStats`, the gameplay statistics per terrain.
- `vegetation.py`: `VegetationStats`, the decoration statistics per terrain, and the pair
  potential and Cox field fits the vegetation sampler reads from them.
