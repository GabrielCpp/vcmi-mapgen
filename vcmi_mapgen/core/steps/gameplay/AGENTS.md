# core/steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in. It reads the `ContentPlan` and the `Accents` with `ctx.get`: a planned home's town stands with `HOME_FOOTING`. After the promised mines it runs the one map-wide pass of `placer.py`.
- `landmark.py`: the accent landmarks. Each accent patch in the `Accents` of 20 tiles or more takes one gold mine, abandoned mine, permanent stat building or dwelling, its doors on the patch. The patch the homes reach last, in travel days, takes a dragon dwelling behind a level-7 guard instead. The landmarks run right after the towns and the shipyards.
- `allocate.py`: the mine promise. Before and after the map-wide pass, `keep_promise` stands the basic mines still missing so every player reaches each basic resource within 14 hero-days and within 3 days of the other players. Wood and ore get one mine per late player behind a level 1 guard. A rare mine stands behind a level 3 guard and serves every player it brings in time. The map is read again after each resource that stood a mine. `GameplayStep` then provides `PromisedWays`, which every later step keeps open.
- `placer.py`: the map-wide pass over the neutral towns, mines, dwellings, banks and visitables. `Placement.plan` turns the quota into slots, and `Placement.place` stands them and tallies the shortfall.
- `quota.py`: how many objects of each family the whole map holds, at the corpus rate per tile times `--density`.
- `bands.py`: the slot of each object: the player and effort band it serves and its target in days, and the order the slots are placed in.
- `reach.py`: `Reach`, the objects of each family each player reaches within each band, and how far one more would spread the players.
- `siting.py`: where each slot stands. It ranks every site tile by the spread it would cause, then by its player's band and target, and skips an object that would spread the players beyond one.
- `pick.py`: `Picker`, which object of a family stands on a site's terrain.
- `fallback.py`: `smaller`, the smaller objects of a pool to try when the drawn one finds no room.
- `economy.py`: the basic mine resources, the mine variants and the dwellings tied to a town.
- `result.py`: `GameplayResult`, each zone's placed objects and remaining tiles, and
  `GateResult`, `TownsIndex` and `PromisedWays`, which `GameplayStep` publishes.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field, and the spread that keeps them apart.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets.
