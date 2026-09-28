# corpus/: statistics over the corpus maps

Code here reads the corpus, loads and saves the priors, and compares the corpus with generated maps. It never runs the pipeline.

## Map

- `maps.py`: the corpus maps: `corpus_path`, `all_map_names`, `load_corpus_map` and `corpus_maps`, each map a `MapState` read through `vcmi.load.load_map`.
- `gates.py`: `load_gate_stats` and `save_gate_stats` over `data/pp/gate_stats.json`.
- `gameplay.py`: `load_gameplay` and `save_gameplay` over the per-level gameplay statistics.
- `mine/`: the miners, one per prior.
- `match.py`: the per-object entrance measures and the per-zone counts behind `cli corpus-match`.
