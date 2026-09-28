# core/

Map generation: the data model, the pipeline engine and the steps.

## Map

- `catalog.py`: the `Catalog` port, `ObjectSpec` and `Trait`. Every question the core asks about objects goes through the `Catalog` a step receives in `run`. A decision that singles out a kind of object asks `types_with(trait)`, so the core never names a VCMI type.
- `grid/`: pure grid algorithms over tile sets: segmentation, components, paths, pockets, edge distance and noise.
- `model/`: `MapState`, the tile grid and object list, and the plain data types.
- `placement/`: where an object stands: footprint cells, the terrain rule, guards, sites, `place_one` and scatter.
- `planning/`: each zone's entrances, walkable web and sea plan, and the one `ZoneRecord` each zone carries.
- `priors/`: the corpus priors as frozen values.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, and the `ProviderRegistry`.
- `steps/`: one subpackage per pipeline step.
- `literals_test.py`: the three string checks an import contract cannot make. No module under
  `core/` names a VCMI animation, a VCMI object type or option key, or a purpose outside
  `model/purpose.py`.
