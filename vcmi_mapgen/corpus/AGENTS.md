# corpus/: statistics over the corpus maps

Code here reads the corpus and compares it with generated maps. It never runs the pipeline.

## Map

- `maps.py`: the corpus maps: `corpus_path`, `all_map_names`, `load_corpus_map` and `corpus_maps`, each map a `MapState` read through `vcmi.load.load_map`.
- `match.py`: the per-object entrance measures and the per-zone counts behind `cli corpus-match`.
