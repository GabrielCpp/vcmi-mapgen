# vcmi_mapgen

## Map

- `cli.py`: the CLI, with `generate`, `render-ontology` and `mine-stats`. It builds the pipeline.
- `mine_stats.py`: which corpus statistics exist and the one pass that rebuilds every `data/pp/` file.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, the `ProviderRegistry` and the `PlacementWorkspace` the placement steps share.
- `steps/`: one subpackage per pipeline step, plus the helpers several steps share.
- `models/`: `MapState`, the tile grid and object list, and the plain data types.
- `kit/`: step-independent helpers: geometry, topology, segmentation, autotiling, the corpus loader, and VCMI config.
- `ontology.py`: object identity, footprints, terrain coupling and decoration category. It is the single source of truth for objects.
- `validate.py`: `TerrainGate`, the terrain placement rule.
- `renderers/`: the PNG renderer with H3 sprites, the playable `.vmap` export, the debug overlays and the ontology catalog.
- `readers/`: loads a `.vmap` back into a `MapState`.
- `vcmi/`: Heroes III as VCMI sees it. `formats/` holds the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs.
- `extract_vmap.py`: regenerates the corpus as editor-openable `.vmap` files.
- `corpus_match.py`: the report comparing object placement in corpus and generated zones.
- `veg_experiment.py`: the M1 experiment that samples vegetation on a real corpus zone and compares run lengths.
