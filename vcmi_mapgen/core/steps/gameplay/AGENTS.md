# core/steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in. It reads the `ContentPlan` with `ctx.get`: a planned home's town stands with `HOME_FOOTING`, and each zone's draw takes its place's reward scale.
- `draw.py`: how many gameplay objects a zone holds, and which ones. `DrawSpec.scale` multiplies the zone's corpus object total. It is 1.0 unless a content plan sets it.
- `economy.py`: the basic mines, the economy pair, the mine ledger and the dwellings tied to a town.
- `result.py`: `GameplayResult`, each zone's placed objects and remaining tiles, and
  `GateResult` and `TownsIndex`, which `GameplayStep` publishes.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field, and the spread that keeps them apart.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets.
