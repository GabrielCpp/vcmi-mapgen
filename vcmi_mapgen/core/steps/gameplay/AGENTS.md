# core/steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in. It reads the `ContentPlan` and the `Accents` with `ctx.get`: a planned home's town stands with `HOME_FOOTING`. Right after the shipyards it stands each player town's own sawmill and ore pit, and after the map-wide pass of `placer.py` it warns about any town with no sawmill or ore pit within 12 tiles.
- `landmark.py`: the accent landmarks. Each accent patch in the `Accents` of 20 tiles or more takes one gold mine, abandoned mine, permanent stat building or dwelling, its doors on the patch. The patch the homes reach last, in travel days, takes a dragon dwelling behind a level-7 guard instead. The landmarks run right after the towns and the shipyards.
- `allocate.py`: the mine promise, a target the step log warns about rather than a gate. Before and after the map-wide pass, `keep_promise` stands the basic mines still missing so every player reaches each basic resource within 14 hero-days and within 3 days of the other players. Wood and ore get one mine per late player behind a level 1 guard. A rare mine stands behind a level 3 guard and serves every player it brings in time. The map is read again after each resource that stood a mine. `GameplayStep` then provides `PromisedWays`, which every later step keeps open.
- `placer.py`: the map-wide pass over the neutral towns, mines, dwellings, banks and visitables. `Placement.plan` turns the quota into slots, and `Placement.place` stands them and tallies the shortfall. The neutral towns stand first, each town's own pair right after them, then every other slot. Each pair mine that stood takes one slot off the resource mines, so the curve still counts every resource mine.
- `supply.py`: `stand_pairs`, one sawmill and one ore pit per town with its entrance within 12 tiles of the town's, stood before any other mine near it. The pair stays outside the quota and the round robin.
- `quota.py`: how many objects of each family the whole map holds, times `--density`. The towns and the resource mines follow their corpus curves over land area and player count, the resource mines less each town's sawmill and ore pit. The weekly producers take the mine rate per tile times their corpus share. Every other purpose follows its corpus rate per tile.
- `bands.py`: the slot of each object: the player and effort band it serves and its target in days, and the order the slots are placed in.
- `reach.py`: `Reach`, the objects of each family each player reaches within each band, and how far one more would spread the players.
- `siting.py`: where each slot stands. It ranks every site tile by the spread it would cause under its weakest fair guard, then by its player's band and target, and skips an object that would spread the players beyond one.
- `fair_guard.py`: `fair_guard`, the weakest guard from level 1 to 4 that keeps the players' reach even at each tile, and `TileGrid`, which takes each tile's worst code within a few tiles. Both work on plain arrays, so the tests draw their grids in ASCII. Towns and mines take no fair guard.
- `pick.py`: `Picker`, which object of a family stands on a site's terrain.
- `fallback.py`: `smaller`, the smaller objects of a pool to try when the drawn one finds no room.
- `economy.py`: the mine variants a terrain shows and the dwellings tied to a town.
- `result.py`: `GameplayResult`, each zone's placed objects and remaining tiles, and
  `GateResult`, `TownsIndex` and `PromisedWays`, which `GameplayStep` publishes.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field, and the spread that keeps them apart.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets. A shipyard counts only when a hero boards its boat water from a walkable tile beside it. `place_link` stands one more shipyard on a player's land for a `Link`.
- `sea_links.py`: `SeaLinks`, the land each player walks and the seas it boards and lands from. Right after the shipyards, `GameplayStep` gives each player apart from a rival by land a shipyard whose sea lands on that rival's land, and warns when none fits. `sea_way` is the way a hero walks and sails to a rival town. `PromisedWays` keeps its land tiles open, so later guards and objects leave every landing free.
