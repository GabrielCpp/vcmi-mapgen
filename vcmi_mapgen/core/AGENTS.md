# core/

Map generation: the data model, the pipeline engine and the steps.

## Map

- `model/`: `MapState`, the tile grid and object list, and the plain data types.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, the `ProviderRegistry` and the `PlacementWorkspace` the placement steps share.
- `steps/`: one subpackage per pipeline step, plus the helpers several steps share.
