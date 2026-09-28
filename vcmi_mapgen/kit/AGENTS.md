# kit/: step-independent helpers

Code here serves several steps or tools and knows nothing about the pipeline order. No
module here has its own `__main__`.

## Map

- `geometry.py`: zone-tile-set primitives: neighbourhoods, edge distance and the open run-length statistic.
- `noise.py`: the seeded value-noise field.
- `objects.py`: the corpus catalog: map names, `load_faithful`, `corpus_maps` and footprint mask expansion.
- `paths.py`: where the VCMI data directory and the repository root are on this machine.
- `pp_cache.py`: how a `data/pp/` statistics file is read and written, and the error when one is missing.
- `render_palette.py`: the terrain colours the renderers use.
- `segmentation.py`: zone segmentation composed with each tile's position inside its zone.
- `terrain_lookup.py`: terrain-code names and the terrain sets shared by the CLI and the steps.
- `terrain_segment.py`: the terrain flood fill and the per-tile static features.
- `tiling.py`: the corpus-learned autotiler that picks each tile's transition view.
- `topology.py`: zone-shape planning: entrances, gates, fronts and pocket detection.
- `vcmi_config.py`: the `(objectClass, objectSubID)` to VCMI `type::subtype` lookup from VCMI's own config.
