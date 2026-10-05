# core/priors/

The corpus priors as frozen values the steps read. `corpus/` loads and saves them, and `corpus/mine/` mines them.

## Map

- `bundle.py`: `Priors`, every prior one generation run reads, the place statistics among them, and `TerrainPriors`, one
  level's macro statistics and Markov tables.
- `effort.py`: `EffortPriors`, the guard toll per level, the band edges in hero-days and one `Offer` per band: its artifact class basket, its Pandora grant (`RewardTier`) and its box count.
- `gates.py`: `GateStats`, the Subterranean Gate counts and spacing per map width.
- `gameplay.py`: `TerrainStats`, the gameplay statistics per terrain, and `GameplayStats`,
  one level's statistics keyed by terrain, and `HEMMED_SHARE`, the corpus share of gameplay objects closed on both flanks.
- `macro.py`: `MacroStats`, the corpus zone areas, terrain shares, terrain adjacency and barrier fractions.
- `pocket_masks.py`: `PocketMask`, one drawn pocket shape in one orientation, as offsets from its guard.
- `places.py`: `PlaceStats`, one level's place counts, sizes, adjacency kinds, shapes, palettes, border kinds, accent rates and sizes, transition widths and raw cuts, the palette region counts and the same-terrain share by role pair, `PlaceCount`, one map's place count beside its players and land, `PaletteCount`, one level's palette region count beside its place count and land, and `PlaceContent`, one corpus place's role, hop count from home, area, reward count and value, and its guards' levels, and `RoadStats`, the corpus road statistics. `RoadStats` pools one `RoadCount` per level, its road, walkable and town counts, beside the crossing counts by role pair and border kind, the surface by hop from home, the dominant-terrain shares and the rewards near a road. `core/planning/content.py` reads the `PlaceContent` rows, and `core/steps/roads/network.py` reads `RoadStats`.
- `markov.py`: `MarkovTables`, the terrain Markov chains that texture zone borders. `TerrainPriors.markov_places` holds the four-neighbour tables counted inside corpus places, which Paint textures with.
- `vegetation.py`: `VegetationStats`, the decoration statistics per terrain, and the pair
  potential and Cox field fits the vegetation sampler reads from them.
