# core/steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in.
- `draw.py`: how many gameplay objects a zone holds, and which ones.
- `economy.py`: the basic mines, the economy pair, the mine ledger and the dwellings tied to a town.
- `result.py`: `GameplayResult`, each zone's placed objects and remaining tiles, and
  `GateResult` and `TownsIndex`, which `GameplayStep` publishes.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field, and the spread that keeps them apart.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets.
- `water.py`: the water-body objects and the seaport guarantee.
