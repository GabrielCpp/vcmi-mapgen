# corpus/: statistics over the corpus maps

Code here reads the corpus, loads and saves the priors, and compares the corpus with generated maps. It never runs the pipeline.

## Map

- `maps.py`: the corpus maps: `corpus_path`, `all_map_names`, `load_corpus_map`, `named_corpus_maps` and `corpus_maps`, each map a `MapState` read through `vcmi.load.load_map`, with one `Terrain` per tile.
- `cache.py`: `read_cache` and `write_cache`, one statistics file under `data/pp/` with its
  version and source stamp.
- `effort.py`: `load_effort`, `save_effort` and `tuned_effort` over `data/pp/effort.json`. `tuned_effort` falls back to the defaults when the file is absent.
- `gates.py`: `load_gate_stats` and `save_gate_stats` over `data/pp/gate_stats.json`.
- `gameplay.py`: `load_gameplay` and `save_gameplay` over the per-level gameplay statistics.
- `macro.py`: `load_macro` and `save_macro` over `data/pp/macro_stats.json` and its underground twin.
- `markov.py`: `load_tables` and `save_tables` over `data/pp/markov_<level>.json`, and `load_inside` and `save_inside` over `data/pp/markov_places_<level>.json`.
- `mines.py`: `load_mines` and `save_mines` over `data/pp/mines.json`, the resource mine curve.
- `places.py`: `load_places` and `save_places` over `data/pp/place_stats.json` and its underground twin. Each `PlaceContent` row is saved as `[role, hop, area, rewards, value, fixed, guards]`, and the road statistics under `roads`.
- `territories.py`: `load_territories` and `save_territories` over `data/pp/territory_stats.json`, one `TerritoryStats` per level.
- `tiler.py`: `load_tiler` and `save_tiler` over `data/pp/tiler.json`, the terrain and the road frame tables. The export and the PNG renderer load it. No step does.
- `vegetation.py`: `load_vegetation` and `save_vegetation` over `data/pp/veg_<terrain>.json`,
  and `vegetation_terrains`, the terrains that have a vegetation file.
- `priors.py`: `load_priors`, which loads every prior above into one `Priors` value. The
  CLI calls it once per run and hands the value to the step constructors.
- `mine/`: the miners, one per prior.
- `match.py`: the per-object entrance measures and the per-zone counts behind `cli corpus-match`.
