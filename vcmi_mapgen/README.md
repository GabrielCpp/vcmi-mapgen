# vcmi_mapgen

## Map

- `cli.py`: the CLI, with `generate` and `render-ontology`. It builds the pipeline.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, the `ProviderRegistry` and the `PlacementWorkspace` the placement steps share.
- `steps/`: one subpackage per pipeline step, plus the helpers several steps share.
- `models/`: `MapState`, the tile grid and object list, and the plain data types.
- `kit/`: step-independent helpers: geometry, reachability, topology, segmentation, autotiling, the corpus loader, VCMI config and `.vmap` I/O.
- `ontology.py`: object identity, footprints, terrain coupling and decoration category. It is the single source of truth for objects.
- `validate.py`: `TerrainGate`, the terrain placement rule.
- `renderers/`: the PNG renderer with H3 sprites, the playable `.vmap` export, the debug overlays and the ontology catalog.
- `readers/`: loads a `.vmap` back into a `MapState`.
- `h3m.py`: the `.h3m` parser.
- `extract_vmap.py`: regenerates the corpus as editor-openable `.vmap` files.
- `corpus_match.py`: the report comparing object placement in corpus and generated zones.
