# vcmi_mapgen

## Map

- `cli/`: the only entry point, with `generate`, `render-ontology`, `regen-ontology`, `mine-stats`, `extract-vmap` and `corpus-match`. `cli/steps.py` holds the one step list.
- `corpus/`: corpus statistics code. `match.py` tallies corpus zones against generated zones.
- `mine_stats.py`: which corpus statistics exist and the one pass that rebuilds every `data/pp/` file.
- `core/`: map generation: `grid/` holds the pure grid algorithms, `model/` holds `MapState` and the plain data types, `pipeline.py` the engine and the `PlacementWorkspace`, and `steps/` one subpackage per step.
- `kit/`: step-independent helpers: topology, autotiling and the corpus loader.
- `validate.py`: `TerrainGate`, the terrain placement rule.
- `renderers/`: the PNG renderer with H3 sprites, the playable `.vmap` export, the debug overlays and the ontology catalog.
- `readers/`: loads a `.vmap` back into a `MapState`.
- `vcmi/`: Heroes III as VCMI sees it. `formats/` holds the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs. `catalog/` holds object identity, footprints, terrain coupling and decoration category, and it is the single source of truth for objects.
- `veg_experiment.py`: the M1 experiment that samples vegetation on a real corpus zone and compares run lengths.
