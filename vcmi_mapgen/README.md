# vcmi_mapgen

## Map

- `cli/`: the only entry point, with `generate`, `render-ontology`, `regen-ontology`, `mine-stats`, `extract-vmap` and `corpus-match`. `cli/steps.py` holds the one step list, and `cli/mine_stats.py` the one pass that rebuilds every `data/pp/` file.
- `corpus/`: corpus statistics code. `maps.py` loads the corpus maps, `gates.py`, `gameplay.py` and `vegetation.py` load and save priors, `mine/` holds miners, `match.py` tallies corpus zones against generated zones, and `cache.py` reads and writes one statistics cache file.
- `core/`: map generation: `grid/` holds the pure grid algorithms, `placement/` where an object stands and the terrain rule, `planning/` each zone's entrances, web and record, `priors/` the corpus priors as values, `model/` holds `MapState` and the plain data types, `pipeline.py` the engine, and `steps/` one subpackage per step.
- `renderers/`: the PNG renderer with H3 sprites, the playable `.vmap` export, the debug overlays and the ontology catalog.
- `vcmi/`: Heroes III as VCMI sees it. `load.py` reads a `.vmap` back into a `MapState`. `formats/` holds the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs. `catalog/` holds object identity, footprints, terrain coupling and decoration category, and it is the single source of truth for objects.
