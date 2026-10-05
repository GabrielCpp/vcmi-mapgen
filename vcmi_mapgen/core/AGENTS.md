# core/

Map generation: the data model, the pipeline engine and the steps.

## Map

- `catalog.py`: the `Catalog` port, `ObjectSpec` and `Trait`. Every question the core asks about objects goes through the `Catalog` a step receives in `run`. A decision that singles out a kind of object asks `types_with(trait)`, so the core never names a VCMI type.
- `grid/`: pure grid algorithms over tile sets: segmentation, components, paths, pockets, edge distance and noise.
- `model/`: `MapState`, the tile grid and object list, and the plain data types.
- `placement/`: where an object stands: footprint cells, the terrain rule, guards, sites, `place_one` and scatter.
- `planning/`: each zone's entrances, walkable web and sea plan, the content plan of each place, the guard level in front of each prize in a cut-off place, and the one `ZoneRecord` each zone carries.
- `priors/`: the corpus priors as frozen values.
- `reading/`: place inference, which reads a finished map back into places, their roles and the kind of each border between them (map-math 3.2). The miner and the place overlay call it. `RoadsStep` reads its walkable tiles with `reading/ground.py`. `reading/paint.py` reads the paint invariants (map-math 1.6): border depth, transition bands and widths, raw cuts, dominant shares, accents and accent locality violations. The miner reads the corpus with it, and Paint shares its border geometry. `reading/measures.py` holds the functionals the miner pools, the raw cut share among them. `reading/palette.py` reads the palette of a place map: the same-terrain share of its borders, its palette region count and the same share by role pair. The miner and the places terrain log line read it. `reading/content.py` reads each place's rewards, their gold-equivalent value from `reading/value.py`, and its guards' levels, keyed by role and hop count from the nearest home (map-math 3.4 and 5.1). The miner pools it into the corpus content table, and `planning/content.py` counts hops with it, so `reading/` sits one import layer below `planning/`. `reading/roads.py` reads a level's roads (map-math 3.4): road share, town links, crossed borders, surface by hop and the dominant-terrain share. The miner pools it into `RoadStats`, and the road tests check generated roads with it. `reading/vector.py` reads one map's reading vector (map-math 8): palette regions, same share, raw cut, the border kind shares, walkable share, zone-of-control share, rewards, guards, home separation, value and guard level by hop, and road share. `reading/verdict.py` holds the corpus spread of each reading and the rule that decides whether a candidate model replaces the default. The `readings` subcommand runs both. `reading/routes.py` reads where a hero can walk, sail and jump, with each tile's terrain cost and guard level, and `reading/effort.py` prices each tile in hero-days from the nearest home: the guard toll plus the travel. The effort miner and `TreasureStep` read it.
- `pipeline.py`: the `PipelineStep` contract, the `Pipeline` engine, and the `ProviderRegistry`.
- `steps/`: one subpackage per pipeline step.
- `literals_test.py`: the three string checks an import contract cannot make. No module under
  `core/` names a VCMI animation, a VCMI object type or option key, or a purpose outside
  `model/purpose.py`.
