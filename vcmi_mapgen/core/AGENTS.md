# core/

Map generation: the data model, the pipeline engine and the steps.

## Map

- `catalog.py`: the `Catalog` port and `ObjectSpec`. Every question the core asks about objects goes through the `Catalog` a step receives in `run`.
- `grid/`: pure grid algorithms over tile sets: segmentation, components, paths, pockets, edge distance and noise.
- `model/`: `MapState`, the tile grid and object list, and the plain data types.
- `placement/`: where an object stands: footprint cells, the terrain rule, guards, sites, `place_one` and scatter.
- `planning/`: each zone's entrances, walkable web and sea plan, and the one `ZoneRecord` each zone carries.
- `priors/`: the corpus priors as frozen values.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, and the `ProviderRegistry`.
- `steps/`: one subpackage per pipeline step.
