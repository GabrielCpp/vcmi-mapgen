# kit/: step-independent helpers

Code here serves several steps or tools and knows nothing about the pipeline order. No
module here has its own `__main__`.

## Map

- `objects.py`: the corpus catalog: map names, `load_faithful`, `corpus_maps`, `purpose_of` through the catalog, and footprint mask expansion.
- `paths.py`: `project_root()`, the repository root.
- `pp_cache.py`: how a `data/pp/` statistics file is read and written, and the error when one is missing.
- `render_palette.py`: the terrain colours the renderers use, keyed by `Terrain`.
- `tiling.py`: the corpus-learned autotiler that picks each tile's transition view.
- `topology.py`: zone-shape planning: entrances, gates and fronts.
