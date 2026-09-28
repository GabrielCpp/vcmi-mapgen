# corpus/: statistics over the corpus maps

Code here reads the corpus, loads and saves the priors, and compares the corpus with generated maps. It never runs the pipeline.

## Map

- `maps.py`: the corpus maps: `corpus_path`, `all_map_names`, `load_corpus_map` and `corpus_maps`, each map a `MapState` read through `vcmi.load.load_map`.
- `gates.py`: `load_gate_stats` and `save_gate_stats` over `data/pp/gate_stats.json`.
- `gameplay.py`: `load_gameplay` and `save_gameplay` over the per-level gameplay statistics.
- `macro.py`: `load_macro` and `save_macro` over `data/pp/macro_stats.json` and its underground twin.
- `markov.py`: `load_tables` and `save_tables` over `data/pp/markov_<level>.json`.
- `vegetation.py`: `load_vegetation` and `save_vegetation` over `data/pp/veg_<terrain>.json`.
- `mine/`: the miners, one per prior.
- `match.py`: the per-object entrance measures and the per-zone counts behind `cli corpus-match`.
