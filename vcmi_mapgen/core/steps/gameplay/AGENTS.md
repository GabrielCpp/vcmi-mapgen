# core/steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in. It reads the `ContentPlan` and the `Accents` with `ctx.get`: a planned home's town stands with `HOME_FOOTING`, and each zone's draw takes its place's reward scale.
- `landmark.py`: the accent landmarks. Each accent patch in the `Accents` of 20 tiles or more takes one gold mine, abandoned mine, permanent stat building or dwelling, its doors on the patch. The patch the homes reach last, in travel days, takes a dragon dwelling behind a level-7 guard instead. The landmarks run right after the towns and the shipyards.
- `fallback.py`: `smaller`, the smaller objects of a pool to try when the drawn one finds no room.
- `draw.py`: how many gameplay objects a zone holds, and which ones. `DrawSpec.scale` multiplies the zone's corpus object total. It is 1.0 unless a content plan sets it.
- `allocate.py`: the mine promise repair. After the zones are placed, `keep_promise` stands the basic mines still missing so every player reaches each basic resource within 14 hero-days and within 3 days of the other players. Wood and ore get one mine per late player behind a level 1 guard. A rare mine stands behind a level 3 guard and serves every player it brings in time. The map is read again after each resource that stood a mine. `GameplayStep` then provides `PromisedWays`, which every later step keeps open.
- `economy.py`: the basic mines, the economy pair, the mine ledger and the dwellings tied to a town.
- `result.py`: `GameplayResult`, each zone's placed objects and remaining tiles, and
  `GateResult`, `TownsIndex` and `PromisedWays`, which `GameplayStep` publishes.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field, and the spread that keeps them apart.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets.
