# Target architecture (draft)

Status: draft, revised 2026-09-28. Nothing here is approved. This revision splits the
generator into a core that knows no game and a `vcmi/` adapter that holds everything
specific to Heroes III as VCMI sees it. `plan.json` beside this file is generated from this
revision. It gives every tracked Python file a fate and every slice its file list.

This draft was drawn on the working tree while the gameplay-after-vegetation work was still
uncommitted (37 files). Slice `s00-oracle` waits until that work lands. Regenerate the plan
then, because paths and importers may have moved.

## What the generator is

One seeded pipeline turns a seed, a size and a subterrain flag into a playable `.vmap`. The
same inputs always give the same map. The corpus of 159 real maps supplies spatial
statistics. The object catalog supplies what can be placed.

Two kinds of knowledge meet in it. Map generation knows zones, entrances, guards, rewards,
footprints, passability and pockets. Heroes III knows that a random level-3 artifact is the
animation `avarnd3`, that water is terrain code 8, that a Seer Hut is the type `seerHut`,
and that a guard's disposition is the option key `character`. The target keeps the first
kind in `core/` and the second in `vcmi/`.

## What a user of the generator feels today

- **Every `generate` waits about 45 s for work that never changes.** The terrain step
  rebuilds its Markov tables and its autotiler tables from the corpus on every run. That
  means 477 map loads, three full passes over the 159 maps. A (seed 1, size 48) run takes
  about 52 s, and about 45 s of it is this rebuild. Slice `s24a`, the second slice, caches
  the tables in `data/pp/` and adds the `mine-stats` command that writes them. Its check
  requires a run under 20 s. The 20 s
  bound is hardcoded, set above the roughly 7 s the profile leaves after the rebuild.
- **Changing what the game offers means editing the steps.** The step code decides by
  comparing Heroes III strings. Across the 47 step, pipeline and validation modules, 25
  purpose names appear as bare strings 168 times, for example `o.purpose != "GUARD"`. A
  typo in one is a silent `False` and a wrong map, not an error. The steps name 54 VCMI
  animations directly, such as `"avarnd3"` and the random-monster list `RND_MON`. They build
  VCMI option dictionaries with keys like `"creatures"`, `"character"` and `"limiter"` in 9
  modules. `WATER = 8` is defined again in 6 modules. A mod, another game version, a banned
  object or a test catalog each means editing step code.
- **A step cannot be tested against a small catalog or small statistics.** Every step reads
  the full ontology through module functions, whatever it is handed. The gate tests patch
  `mine_gate_stats` and the corpus tests patch `faithful_path` to control their inputs.
- **A change to one step can break a later step silently.** The placement steps share one
  mutable `PlacementWorkspace`. A step reading a field an earlier step never filled gets an
  empty default and draws a wrong map, not an error. Slice `s23` replaces it with typed
  results that a missing producer turns into `MissingProviderError`.
- **There is no map-equality check.** A refactor today is judged by eye on a rendered PNG.
  Slice `s00` adds `make golden`, and every slice after it runs it.
- **New code has no obvious home.** `kit/` mixes file formats, grid algorithms, corpus
  loading, autotiling and a render palette. `steps/` holds helpers several steps share. The
  section "Where new code goes" says where each kind of new code goes.

## The three rings

The layout follows the ports-and-adapters contract in the `hexagonal-architecture` skill.

- **`core/`: map generation.** It holds the vocabulary generation reasons with, the grid
  algorithms, planning, placement, the pipeline and the steps. It names no Heroes III object,
  animation, type, terrain code, mask character or option key. It reads no file and imports
  nothing outside `core/`, the standard library, numpy and numba.
- **Ports that `core/` owns.** `core/catalog.py` declares `Catalog`, the one question
  surface about objects. `core/priors/` declares the corpus statistics as frozen value
  types. The core depends on these declarations and never on who fills them.
- **Adapters.** `vcmi/` implements `Catalog` from the VCMI tables and translates a finished
  `MapState` into a `.vmap`. `corpus/` reads `data/pp/` into the prior types and mines those
  files from the corpus maps. `renderers/` draws PNGs and overlays.
- **The composition root.** `cli/` builds the `VcmiCatalog`, loads the priors, builds the
  step list, runs the pipeline and calls the renderers. It is the only package that imports
  every ring.

A test builds a small in-memory catalog and small priors and hands them to a step. No test
patches a module global.

## The core vocabulary

These types replace the strings, integers and masks the steps compare today.

| Type | Module | Replaces |
|------|--------|----------|
| `Purpose` StrEnum and its groups (`COUNTED`, `VISIT_PURPOSES`) | `core/model/purpose.py` | 168 bare purpose strings; `ontology.visitable_purposes()`, which returns a constant |
| `Terrain` IntEnum with `is_water`, `is_barrier`, `is_land` | `core/model/terrain.py` | `WATER = 8` in 6 modules, `WATER, ROCK = 8, 9`, and terrain names compared as strings |
| `Resource` StrEnum | `core/model/resource.py` | `"gold"`, `"wood"` and the other resource strings |
| `ObjectKind` | `core/model/objects.py` | An opaque token for one placeable object. Only the adapter reads its content. Today the adapter uses the animation name. |
| `Footprint` of cells relative to the anchor, each with a `Role` | `core/model/objects.py` | `Mask`, the tuple of `B`, `A`, `V`, `X` strings |
| `ObjectSpec(kind, purpose, footprint, blocking)` | `core/catalog.py` | `Identity(type, subtype, animation, mask)`, which is VCMI's shape |
| `Guard`, `Reward`, `Quest` and the `Payload` union | `core/model/payload.py` | The VCMI `options` dictionaries built in 9 step modules |

`Terrain` values are the core's own. The adapter maps them to Heroes III terrain codes and
VCMI tile prefixes. The two coincide today, so the map does not change.

`PlacedObject` becomes `tile`, `level`, `purpose: Purpose`, `kind: ObjectKind`,
`footprint: Footprint`, `payload: Payload | None`, and the flags `seal`, `cache` and
`pocket_guard`. It loses `type`, `subtype`, `animation`, `mask`, `options` and
`visitable_from`. The adapter derives each of those at export.

## The `Catalog` port

`core/catalog.py` declares it as a `typing.Protocol`. Every parameter and return is a core
type. It returns candidates in a fixed order, because every draw depends on that order. The
VCMI adapter keeps today's sort by animation, so the map does not change.

| Method | Answers | Replaces today |
|--------|---------|----------------|
| `candidates(purpose, terrain)` | the objects serving a purpose that may stand on a terrain | `pool`, `gameplay_pool`, `pick`. `pick` becomes one `rng.choice` in `core/placement/identity.py`. |
| `spec(kind)` | the footprint, purpose and blocking flag of one kind, or `None` when unknown | `identity_of`, `mask_of`, `full_mask_of`, `footprint_size`, `is_blocking`, `has_animation` |
| `allowed_on(kind, terrain)` | whether a kind may stand on a terrain | `allowed_on`, through `TerrainGate` |
| `decor(terrain, *, blocking)` | the decoration candidates for a terrain | `decor_pool`. The `EXCLUDE_DECOR_TYPES` filter moves into the adapter. |
| `decor_category(kind)`, `decor_categories()` | the decoration category of a kind, and the full list | `category_of`, `veg_categories` |
| `mine(resource)` | the mine kind for a resource | `mines_by_resource` |
| `guard(level)` | the random-monster kind for a strength level | `RND_MON`, `rnd_monster` |
| `random_artifact(tier)` | the random-artifact kind for a tier | `ART_BY_LVL`, the `"avarnd*"` literals |
| `portals()` | the two-way portal kinds, in pairing order | `PORTAL_ANIMS` |
| `quest_givers(terrain)` | the kinds that can hold a quest | `pool("QUEST_GATE")` filtered on `type == "seerHut"` |
| `spells(level)`, `artifacts(tier)`, `monsters(level)` | graded draws for reward payloads | `spells_by_level` and the queries `s20` would have added |

### Restrictions live in the catalog

What a map may contain is game content, so the ontology owns it. A map header lists the
allowed spells, artifacts and heroes, and a map may ban objects. The core never sees a ban.
It sees fewer candidates.

- **Per map.** `VcmiCatalog` is built with a `Restrictions` value. Every query applies the
  map-wide bans before it answers, so `candidates`, `guard`, `random_artifact`, `spells`,
  `artifacts` and `monsters` never return a banned kind.
- **One owner for both sides.** `vcmi/export.py` writes the header's allowed lists from the
  same `Restrictions` value the catalog filters with. The placed objects and the header
  cannot disagree.
- **Draw order stays fixed.** A ban removes candidates from the ordered list and never
  reorders it. With no restrictions, every answer is today's answer, so `make golden` holds.

`Restrictions` lives in `vcmi/catalog/restrictions.py` and names VCMI kinds, spells,
artifacts and heroes. `cli` builds it and hands it to `VcmiCatalog`. Nothing exists to build it from yet, so the first version is the empty
value.

Per-zone restrictions are not supported. VCMI templates ban objects per zone, but the
generator's zones come from terrain segmentation, not from a template, so no zone has a
template counterpart to take bans from.

The port never carries the catalog's own browsing and translation calls: `build_tree`,
`iter_leaves`, `name_of`, `resolve`, `cluster_of`, `decode_identity`, `cls_sub_of`,
`vmap_mask_of`, `category_terrain_matrix` and `regenerate`. Those stay inside `vcmi/`,
where `render-ontology`, the exporter and the miners call them.

The pipeline holds one catalog for a run. `Pipeline(catalog, size)` passes it to every step
as `run(self, catalog: Catalog, map_state: MapState)`. The `Ontology` class today has the
same signature and no state. It is replaced by the port, and the parameter starts to mean
something, because all 62 lookups go through it instead of 3.

## The corpus priors

`core/priors/` holds one frozen dataclass per statistics family: `MacroStats`,
`MarkovTables`, `GateStats`, `GameplayStats`, `VegetationStats`. They are
values with no loader. A prior keys by core vocabulary, or by `ObjectKind` when it counts
specific objects. The core never spells a kind.

`cli` loads the priors once through `corpus/`, before the pipeline starts, and passes each
step the priors it needs through its constructor. That fits the step contract, since the
priors are known before any step runs. The gate tests then build a `GateStats` and pass it
in, and the patches of `mine_gate_stats` and `faithful_path` go away.

## Core models and the facts they own

| Fact | Owner | Notes |
|------|-------|-------|
| Tile terrain | `core.model.MapState.terrain` | One grid of `Terrain` per level, after despeckle. Replaces `surfs` and `cells` in `s31`. |
| Tile art | `vcmi/tiles.py`, computed when a map is written or drawn | Which picture each tile shows. Never stored on MapState. |
| Placed objects | `core.model.MapState.objs` | Additive: a step appends, never moves or removes. |
| Gate blocking tiles | `core.model.MapState.gate_blk` | Also held by `GateResult`. Named debt, out of scope. |
| Player towns | `core.model.MapState.player_towns` | |
| Zones and tile-to-zone | `Segmentation`, provided by terrain_gen | Leaves MapState in `s12`. |
| Generation vocabulary | `core/model/` | `Purpose`, `Terrain`, `Resource`, `ObjectKind`, `Footprint`, payloads. |
| What can be placed where | `Catalog`, implemented by `vcmi.catalog.VcmiCatalog` | The corpus never decides identity, footprint or category. |
| Heroes III identity, mask, option shape, terrain code | `vcmi/` | Tables load from `data/ontology/*.json`. |
| Corpus statistics | `core/priors/` types, filled by `corpus/` from `data/pp/` | Mined only by `cli mine-stats`. |
| Cross-step values | typed dataclasses in `core/steps/<name>/result.py` | Replace `PlacementWorkspace`. |

## Sources of truth

- The step list: `cli/steps.py` `build_steps`. `corpus_match` uses it too.
- What the generator may place: the `Catalog` passed to the pipeline. In production that is
  `VcmiCatalog`.
- Heroes III facts: `vcmi/`. No other package spells an animation, type, mask character,
  terrain code or option key.
- Statistics: the files under `data/pp/`. Runtime reads them. Only `cli mine-stats` writes
  them.
- Map equality: `data/golden.json`, checked by `make golden`.

## Target tree

Each line names the one kind of thing the directory holds.

```
vcmi_mapgen/
  core/                map generation; names no game, reads no file
    model/             value types: MapState, PlacedObject, Footprint, ObjectKind,
                       Terrain, Purpose, Resource, payloads
    catalog.py         the Catalog port and ObjectSpec
    priors/            corpus statistics as frozen value types, no loaders
    grid/              pure grid algorithms: geometry, noise, segment, components, reach,
                       paths, pockets
    placement/         placing one object legally: footprint, cells, rules, guards,
                       identity, intensity, rewards, site, place, scatter
    planning/          whole-map plans: zone_plan, zone_index, entrances, borders,
                       player_zones
    pipeline.py        the engine: PipelineStep, Pipeline, ProviderRegistry
    steps/             one package per pipeline step: step.py, result.py, private helpers
  vcmi/                Heroes III as VCMI sees it
    catalog/           tables, objects, decor, graded, loot, regen; VcmiCatalog
    formats/           vmap/, h3m, lod, defs, json_value
    config.py          resolve(obj_class, obj_subid) from the install's config
    install.py         finds the VCMI install in the environment it is handed
    terrain.py         Terrain to Heroes III code, VCMI tile prefix and name
    export.py          MapState to VmapDocument
    load.py            a .vmap file to MapState, the inverse of export
    players.py         player and team setup for the header
  corpus/              loaders from data/pp into core.priors; mine/ holds the miners;
                       maps.py loads corpus maps; match.py tallies corpus against generated
  renderers/           png, sprites (compositing), palette, overlays, ontology_render, vmap
  cli/                 composition root and entry points: generate, render-ontology,
                       extract-vmap, corpus-match, audit, mine-stats, render-sprites,
                       veg-experiment; settings.py resolves the environment once
```

`kit/`, `readers/`, `ontology.py`, `validate.py` and the top-level `models/` disappear.
`steps/segment/` folds into `core/steps/terrain_gen/`. `steps/gate/` holds no step and
splits into corpus, placement and terrain_gen.

## Packages, module by module

The origin column names today's file. `(s)` marks a split, where only part of the file
lands here. `(m)` marks a merge of several files. A blank origin marks a module a slice
creates.

### `core/model/`: value types, no behaviour beyond construction

| Module | Origin | Holds |
|--------|--------|-------|
| `map_state.py` | `models/map_state.py` | `MapState`: size, terrain, gate_blk, objs, player_towns, `add_objs`. Loses `zones` in `s12`. `terrain` replaces `surfs` and `cells` in `s31`. |
| `objects.py` | `models/objects.py` | `PlacedObject`, `ObjectKind`, `Footprint`, `Tile`, `Role`, `footprint(obj)`. Loses `Identity` and `Mask` to `vcmi/`, and `Cell` to `vcmi/tiles.py`. |
| `terrain.py` | `kit/terrain_lookup.py` (s) | `Terrain` IntEnum and its properties. Codes, prefixes and names go to `vcmi/terrain.py`. |
| `purpose.py` | | `Purpose` StrEnum and the purpose groups the steps filter by. |
| `resource.py` | | `Resource` StrEnum. |
| `payload.py` | | `Guard`, `Reward`, `Quest`, `Payload`. Designed in `s30` from the option keys in use. |

### `core/catalog.py` and `core/priors/`: what the core asks for

`catalog.py` holds the `Catalog` Protocol and `ObjectSpec`. `priors/` holds one module per
statistics family, named after the family: `macro.py`, `markov.py`,
`gates.py`, `gameplay.py`, `vegetation.py`. Neither imports anything outside `core/model/`.

### `core/grid/`: pure algorithms over tiles, no objects and no catalog

| Module | Origin | Holds |
|--------|--------|-------|
| `geometry.py` | `kit/geometry.py` | `edge_dist`, `run_lengths`. |
| `noise.py` | `kit/noise.py` | `value_noise`. |
| `segment.py` | `kit/terrain_segment.py`, `kit/segmentation.py` (m) | `segment`, `segment_level`, `compute_static_features`, `canonical_coords`. One public entry, `segment_level`. |
| `components.py` | `steps/vegetation/islands.py` (m), `steps/gameplay/site.py` (s) | `open_islands`, `components`. |
| `reach.py` | `steps/portal/geometry.py` (s) | The one BFS family: 4- and 8-connected reach, walk-and-hard cells. `s21` routes the copies here. |
| `paths.py` | `kit/topology.py` (s) | `geodesic_path`, `farthest_points`. |
| `pockets.py` | `kit/topology.py` (s), `models/pockets.py` (m) | `find_pockets`, `pocket_depths`, `mouth_key`, and the pocket type aliases. |
| `pocket_masks.py` | new | `parse_masks`, which reads the pocket shapes drawn in `data/pockets.txt` into `core/priors` `PocketMask` values. |

### `core/placement/`: placing one object legally

| Module | Origin | Holds |
|--------|--------|-------|
| `footprint.py` | `kit/objects.py` (s), `steps/gameplay/site.py` (s), `steps/gate/gates.py` (s), `steps/vegetation/border_plan.py` (s) | `footprint_cells`, `blocking_cells`, `interactive_cells`, `overlay_clear`, `front_tiles`. One decode, over `Footprint` instead of mask strings. |
| `rules.py` | `validate.py` | `TerrainGate(catalog)`, `footprint_violations`. The rule `MapState.add_objs` checks. |
| `cells.py` | `steps/gameplay/water.py` (s) | `CellRules`, `legal_cells`. |
| `identity.py` | `steps/gameplay/draw.py` (s), `steps/gameplay/water.py` (s) | `pick_kind`: one draw over `catalog.candidates` for draw and water. |
| `intensity.py` | `steps/gameplay/draw.py` (s) | `density`, `stoch_round`, and the intensity weights. |
| `guards.py` | `steps/placement.py` (s), `steps/gate/gates.py` (s) | `GUARD_SPACING`, `guard_zoc`, `guard_spaced`, `Clearance`, `fits`. The guard kind comes from `catalog.guard(level)`. |
| `place.py` | `steps/placement.py` (s) | `PlaceTarget`, `PlaceSpec`, `place_one`, `web_dist`, `scatter_reach`. |
| `rewards.py` | `steps/placement.py` (s), `steps/loot/caches.py` (s) | One reward builder returning a `Reward` payload. Replaces `_pandora_reward` and `_seerhut_reward`, which build VCMI dictionaries. |
| `site.py` | `steps/gameplay/site.py` (s) | `LevelField`, `ZoneSite`, `SiteIndex`, `back_score`, `door_cells`, `path_to_web`, `mend`. |
| `scatter.py` | `steps/scatter/scatter.py` | `ScatterZone`, `ScatterConfig`, `place_scatter`. Used by the scatter step and by loot. |

### `core/planning/`: whole-map decisions made before objects land

| Module | Origin | Holds |
|--------|--------|-------|
| `zone_plan.py` | `steps/zone_plan.py` | `plan_zones`, `SeaPlan`, `plan_landings`, `seaport_cells`, `populate_water`. Returns a `ZonePlan`. |
| `zone_index.py` | `steps/zone_index.py`, `models/zone_record.py` (m) | `ZoneIndex`, `ZoneRecord`, `build_zone_index`. One record per zone. |
| `entrances.py` | `kit/topology.py` (s) | `plan_entrances`, `zone_fronts`, `zone_gate_bands`, `zone_gates`, `Entrance`. |
| `borders.py` | `steps/vegetation/border_plan.py` (s) | `zone_owner`, `cross_pairs`. Border and vegetation both read them, so neither imports the other. |
| `player_zones.py` | `steps/gameplay/mines.py` (s) | `select_player_zones`. |

### `core/steps/`: one package per step

| Step | Modules after the plan | Notes |
|------|------------------------|-------|
| `terrain_gen` | `step.py`, `result.py`, `macro.py`, `texture.py`, `despeckle.py`, `gate_sites.py` | Absorbs `SegmentStep` in `s12`. Writes `MapState.terrain`. Provides `TerrainGrids` and `Segmentation`. Takes `MacroStats`, `MarkovTables`, `GateStats`. Picks no tile art. |
| `vegetation` | `step.py`, `result.py`, `sample.py`, `border_plan.py` | `sample.py` loses `m1_experiment` to `cli/veg_experiment.py`. Takes `VegetationStats`. |
| `gameplay` | `step.py`, `result.py`, `draw.py`, `economy.py`, `water.py`, `shipyards.py`, `gate_pairs.py` | `economy.py` holds `ECONOMY`, `mine_variants`, `rest_mines`, `tie_dwellings`, keyed by `Resource`. Takes `GameplayStats`. |
| `gated` | `step.py`, `result.py`, `placer.py` | |
| `treasure` | `step.py`, `result.py`, `fill.py` | `s26` rewrites `fill.py` as one pass. |
| `border` | `step.py`, `result.py`, `entrances.py`, `crossings.py` | `crossings.py` is today's `border_seal.py`. |
| `portal` | `step.py`, `result.py`, `rescue.py` | Portal kinds come from `catalog.portals()`. |
| `loot` | `step.py`, `result.py`, `pockets.py`, `quests.py`, `pickups.py`, `reward_zone.py` | `caches.py` (985 lines) splits three ways. Quest givers come from `catalog.quest_givers`. |
| `scatter` | `step.py` | Its algorithm lives in `core/placement/scatter.py`. |

### `vcmi/`: Heroes III as VCMI sees it

| Module | Origin | Holds |
|--------|--------|-------|
| `catalog/tables.py` | `ontology.py` (s) | `TAXONOMY`, `LEAF_META` loaded lazily from `data/ontology/{taxonomy,leaf_meta}.json`; `CLASS_NAMES`, `MONSTER_LEVELS`, `SPELL_LEVELS`, `ARTIFACT_TIERS`; `RESOURCE`, `MINE_RES`, `FACTION`, `PURPOSE`, `CLUSTERS`, `GATE_TYPES`, `GATE_NAMES`, `GATE_COLORS`, `RELATIONAL`, `TERRAIN_COUPLED`, `DECOR_NAMES`, `COLOR_KEYED_NAMES`, `SUBTYPE_KEYED_NAMES`; `LeafMeta`, `ClassInfo`. |
| `catalog/objects.py` | `ontology.py` (s) | The table queries behind the port, and `build_tree`, `iter_leaves`, `name_of`, `resolve`, `cluster_of`, `decode_identity`, `cls_sub_of`. |
| `catalog/decor.py` | `ontology.py` (s), `kit/terrain_lookup.py` (s) | Decoration pools, categories, `category_terrain_matrix`, `EXCLUDE_DECOR_TYPES`. |
| `catalog/graded.py` | `steps/gate/gates.py` (s), `steps/loot/caches.py` (s) | Spells, artifacts and monsters by level or tier; the random-monster and random-artifact animations. Replaces `RND_MON`, `ART_BY_LVL` and the `"avarnd*"` literals. |
| `catalog/regen.py` | `ontology.py` (s) | `regenerate`: rebuilds the two JSON tables from the editor's `objects.txt`. Only `cli` calls it. |
| `catalog/adapter.py` | `ontology.py` `Ontology` (s) | `VcmiCatalog`, the implementation of `Catalog`. It maps `ObjectKind` to animation and a mask to a `Footprint`, and applies `Restrictions`. |
| `catalog/restrictions.py` | | `Restrictions`: map-wide bans and the header's allowed spells, artifacts and heroes. |
| `formats/vmap/` | `kit/vmap/*` | `VmapDocument`, reader, writer, mask charset, terrain strings, `visitable_from`. The reader is the one way any code reads a `.vmap`, including the 159 corpus maps in `data/corpus/vmap/`. |
| `formats/h3m.py` | `h3m.py` | `parse_file`, `H3Map`. Moves whole. |
| `formats/lod.py` | `kit/lod.py` | LOD archive index. |
| `formats/defs.py` | `renderers/sprites.py` (s) | `parse_def`, `_decode_frame` for DEF formats 0 to 3. |
| `formats/json_value.py` | `kit/json_value.py` | Typed accessors over relaxed JSON. |
| `config.py` | `kit/vcmi_config.py` | `resolve(obj_class, obj_subid)`. It reads the config directories of the `VcmiInstall` it is handed. |
| `install.py` | `kit/paths.py` | `VcmiInstall(home, data_dir, config_dirs)` and `find_install(env, platform)`, which tries each platform convention in order and raises naming `VCMI_HOME` when none exists. It reads no global and lists no directory at import. |
| `terrain.py` | `kit/terrain_lookup.py` (s), `renderers/overlays/_tiles.py` (s) | `Terrain` to Heroes III code, VCMI tile prefix and display name. One table. |
| `tiles.py` | `kit/tiling.py` (s), `kit/vmap` `tile_string` (s) | Tile art: `Cell`, `TilerTables`, `tile(terrain, tables)` giving each tile its frame and flip, `tile_string`. Also the terrains whose tilesets can draw a shape one tile wide, which despeckle takes as an argument instead of hardcoding `_EROSION_EXEMPT`. |
| `load.py` | `readers/vmap_reader.py`, `kit/objects.py` `load_faithful` (s), `renderers/sprites.py` `read_vmap`, `read_real`, `_adapt` (s) (m) | `load_map(path) -> MapState`: VCMI type and animation to `ObjectKind` and purpose through `VcmiCatalog`, tile strings to the `Terrain` grid. Today the same translation is written three times, once per shape: `VmapReader` gives a MapState, `load_faithful` a `FaithfulMap`, `_adapt` a surface and an object list. |
| `export.py` | `renderers/vmap.py` (s), option builders in 9 step modules (s) | `MapState` to `VmapDocument`: kind to type, subtype and animation; footprint to mask; payload to options; `visitable_from`. |
| `players.py` | `renderers/vmap.py` (s) | `parse_teams`, `_apply_playability`. |

`ontology.py` is 4,248 lines today. The two literal tables fill lines 503 to 3461, so the
code shrinks to about 1,300 lines across the catalog modules once the tables move to JSON.
Loading JSON is I/O, and it is allowed here because `vcmi/` is an adapter.

### `corpus/`: fills `core.priors` from `data/pp/`; `corpus/mine/` builds `data/pp/`

| Cache file | Miner (target) | Loader (target) | Prior type | Origin | Steps given it |
|------------|----------------|-----------------|------------|--------|----------------|
| `macro_stats.json`, `macro_stats_underground.json` | `mine/macro.py` | `macro.py` | `MacroStats` | `terrain_gen/macro_topo.py` | terrain_gen |
| `markov_<level>.json` (new) | `mine/markov.py` | `markov.py` | `MarkovTables` | `terrain_gen/markov.py` `learn`, `learn4` | terrain_gen |
| `tiler.json` (new) | `mine/tiler.py` | `tiler.py` | `TilerTables`, defined in `vcmi/tiles.py` | `kit/tiling.py` `_learn_terrain_tiler` | no step; `vcmi/export.py` and `renderers/png.py` |
| `gate_stats.json` | `mine/gates.py` | `gates.py` | `GateStats` | `steps/gate/gates.py` | terrain_gen |
| `gameplay_stats.json`, `gameplay_stats_underground.json` | `mine/gameplay.py` | `gameplay.py` | `GameplayStats` | `steps/gameplay/mines.py` | vegetation (zone plan), gameplay, gated, treasure, portal, loot, scatter |
| `veg_<terrain>.json` (8 files) | `mine/vegetation.py` | `vegetation.py` | `VegetationStats` | `steps/vegetation/stats.py` | vegetation |

- A loader translates the file's keys into core vocabulary. The files may keep VCMI names.
  The tiler loader is the exception: tile art is VCMI's, so its type lives in
  `vcmi/tiles.py` and no step receives it.
- `corpus/maps.py` holds `corpus_path(name)`, `all_map_names` and `load_corpus_map(name)`,
  which calls `vcmi.load.load_map` on `data/corpus/vmap/<name>.vmap`. A corpus map is a
  `MapState`, like a generated one, so a miner, a renderer and `corpus-match` read both the
  same way. `FaithfulMap` goes. Only miners and `cli` import `corpus/maps.py`. The tiler
  miner reads tile strings through `vcmi/formats/vmap/reader.py`, because MapState carries
  no tile art.
- `corpus/match.py` holds the corpus-versus-generated tally behind `cli corpus-match`.
- `cli mine-stats` rebuilds every cache, and `--only <name>` rebuilds one. Each file records
  its builder under a `_source` key. A loader that finds its file missing, or at the wrong
  `_version`, raises an error naming that command.
- `cli` loads each file once per run. Today `mine_gameplay` re-parses its file on each of its
  35 calls per run. That costs 0.1 s, so the fix is for correctness of the rule, not for
  time.
- `data/objlib.json` has no writer in the tree. It loses its last reader in `s07`, which
  deletes it.

### `renderers/` and `cli/`

- `renderers/`: `png.py`, `sprites.py` (compositing only), `palette.py`,
  `ontology_render.py`, `overlays/`, and `vmap.py`, which calls `vcmi/export.py` and the
  writer. A renderer reads MapState and registry values and writes a file. It never places.
  `png.py` and `vcmi/export.py` each call `vcmi.tiles.tile` on `MapState.terrain`. Tiling
  draws no random number, so both get the same art.
- `cli/`: `__main__.py` (argument parsing), `generate.py`, `steps.py` (`build_steps`, the one
  step list), `extract_vmap.py`, `corpus_match.py`, `audit.py` (`audit_variety`),
  `render_sprites.py`, `veg_experiment.py`, `mine_stats.py`, and `settings.py`. `generate.py`
  is the composition root: it builds `VcmiCatalog`, loads the priors and hands both to the
  steps. `settings.py` holds `Settings.from_env(environ, platform)`, the one place that reads
  the environment. It finds the VCMI install only when the command needs it.

## Pipeline data flow

Steps run in list order: terrain, segment, vegetation, gameplay, gated, treasure, border,
portal, loot, scatter. The registry carries typed values between them. Order still
matters, because MapState writes and RNG draws depend on it.

### The step contract, after `s28` and `s24b`

- **Constructor.** Config and collaborators known before any step runs: seed, size, player
  count, the subterrain flag, and the priors the step reads.
- **`inject(self, ctx)`.** The step pulls values earlier steps produced.
- **`run(self, catalog: Catalog, map_state: MapState)`.** The step asks the catalog and
  writes onto `map_state`.

### Today

| Step | Requires | Provides | Workspace fields it writes |
|------|----------|----------|----------------------------|
| terrain | | `TerrainGrids` | |
| segment | | | MapState `zones` |
| vegetation | `TerrainGrids` | `VegetationResult` | creates the workspace; zone plan fields; `blocked`, `open_set`, `passable`; `sea`, `seaport_*` |
| gameplay | `TerrainGrids` | `GateResult`, `TownsIndex` | `gobjs`, `occupied`, `gblocked`, `approaches`, `reach`, `prot`; narrows `open_set`, `passable`; `sea`, `seaport_*`, `town_of_zone` |
| gated | workspace | `ZoneIndex`, `GatedResult` | `hard_avoid`; adds to `blocked`, `used` |
| treasure | `ZoneIndex`, `GatedResult` | | adds to `used` |
| border | `TerrainGrids`, `TownsIndex`, `ZoneIndex` | `BorderResult` | `guard_tiles`; adds to `blocked`; narrows `open_set` |
| portal | `TerrainGrids`, `GateResult` (default), `TownsIndex`, `ZoneIndex` | `PortalResult` | adds to `occupied`, `used` |
| loot | `TownsIndex`, `ZoneIndex` | `LootResult` | adds to `used` |
| scatter | `ZoneIndex` | | |

Vegetation and gameplay both call `get_or_create(PlacementWorkspace)`. Whichever runs first
creates it. Every placement step after them reads and writes the same instance.

### Target, after `s23`

| Step | Requires | Provides |
|------|----------|----------|
| terrain_gen | | `TerrainGrids`, `Segmentation` |
| vegetation | `TerrainGrids`, `Segmentation` | `ZonePlan`, `VegetationResult` |
| gameplay | `TerrainGrids`, `Segmentation`, `ZonePlan`, `VegetationResult` | `GameplayResult`, `GateResult`, `TownsIndex` |
| gated | `ZonePlan`, `VegetationResult`, `GameplayResult` | `ZoneIndex`, `GatedResult` |
| treasure | `ZoneIndex`, `GatedResult` | `TreasureResult` |
| border | `TerrainGrids`, `Segmentation`, `ZonePlan`, `TownsIndex`, `ZoneIndex` | `BorderResult` |
| portal | `TerrainGrids`, `Segmentation`, `GateResult`, `TownsIndex`, `ZoneIndex`, `GameplayResult` | `PortalResult` |
| loot | `TownsIndex`, `ZoneIndex`, `BorderResult` | `LootResult` |
| scatter | `Segmentation`, `ZoneIndex` | |

Every `require` is a hard `require`. Portal stops reading `GateResult` through `get` with a
default, because gameplay always runs before it.

## What replaces `PlacementWorkspace`

The workspace holds 16 per-zone fields and 8 per-level fields. Each field gets one producer
and one result type.

### Values written once

| Field | Target owner | Result type |
|-------|--------------|-------------|
| `terrain`, `ts`, `ts_full` | zone plan | `ZonePlan.zones[zid]` |
| `entrances`, `rim8`, `ent_bands` | zone plan | `ZonePlan.zones[zid]` |
| `entrance_plan`, `ridge` | zone plan | `ZonePlan.levels[level]` |
| planned `seaport_blk`, `seaport_appr` | zone plan | `ZonePlan.levels[level].landings` |
| `gobjs`, `gblocked`, `approaches`, `reach` | gameplay | `GameplayResult.zones[zid]` |
| final `prot` | gameplay | `GameplayResult.zones[zid].prot`. The zone plan's `prot` stays in `ZonePlan` as the planned web. |
| `town_of_zone` | gameplay | `GameplayResult.town_of_zone` |
| actual `seaport_blk`, `seaport_appr`, `sea` | gameplay | `GameplayResult.levels[level]` |
| `hard_avoid` | gated | `ZoneIndex.hard_avoid` |
| `guard_tiles` | border | `BorderResult.guard_tiles` |

### Values later steps narrow

Five fields change after their first writer: `blocked`, `open_set`, `passable`, `occupied`
and `used`. `s33` takes `used` out first, because it records the same claims the cover
index already refuses overlaps on. The cover index owns the claims and gives the undo, and
`used` goes. Two designs fit the other four, and `s23` picks per field by running
`make golden`.

1. **Derived.** The field is a function of MapState. For example, `occupied` may equal the
   covered tiles of the zone's gameplay objects. `s23` writes the derivation in `core/placement/cells.py`
   and tests it for equality against the workspace field at every step boundary on both
   golden maps. A field that matches everywhere becomes the function, and nothing stores it.
2. **Deltas.** A field that does not match stays explicit. Its first writer publishes the
   base set, and each later writer publishes what it removed or added in its own result.
   `core/placement/cells.py` folds them in pipeline order: `open_set(zid) = veg.open_set -
   gameplay.taken - border.taken`. A step never mutates another step's result.

The test runs before any caller changes. That makes it a reading, not a design argument.

Once the four fields have owners, `ZoneRecord` holds only what the zone plan fixed, and
`s23` freezes it.

## Registry types, after `s11`

Each step's results live in `core/steps/<name>/result.py`. A step may import another step's
`result`, and nothing else from it.

| Module | Types |
|--------|-------|
| `terrain_gen/result.py` | `TerrainGrids(tunnel_protect)`, which loses `grids` to `MapState.terrain` in `s31`; `Segmentation(zones, zone_label)` (from `s12`) |
| `vegetation/result.py` | `VegetationResult(log, zones)`; `ZonePlan` is defined in `core/planning/zone_plan.py` and provided by vegetation |
| `gameplay/result.py` | `GameplayResult` (from `s23`), `GateResult(gate_objs, gate_blk)`, `TownsIndex(player_zids)` |
| `gated/result.py` | `GatedResult(access)`; `ZoneIndex` is defined in `core/planning/zone_index.py` and provided by gated |
| `treasure/result.py` | `TreasureResult` (from `s23`, only when a field treasure narrows does not derive) |
| `border/result.py` | `BorderResult(log, guard_tiles)` |
| `portal/result.py` | `PortalResult(log)` |
| `loot/result.py` | `LootResult(pockets)` |

## Import contract

Checked by import-linter from `s25-contracts`. Top imports bottom, never the reverse.

Outer ring:

1. `cli`
2. `renderers`
3. `corpus`
4. `vcmi`

Core:

5. `core.steps`
6. `core.pipeline`
7. `core.planning`
8. `core.placement`
9. `core.grid`
10. `core.catalog` | `core.priors`
11. `core.model`

- `core` imports nothing outside `core`, the standard library, numpy and numba.
- `core.steps.*` are independent. The one allowed crossing is a step importing another
  step's `result`.
- `corpus.mine` and `corpus.maps` are imported only by `cli`.

Three grep checks run beside import-linter, because an import contract cannot see a string:

- No string literal naming a VCMI animation under `core/`. The pattern is `"av[a-z0-9]+"`.
- No VCMI object type or option key as a string literal under `core/`, for example
  `"seerHut"`, `"pandoraBox"`, `"shipyard"`, `"creatures"`, `"character"`, `"limiter"`.
- No purpose name as a string literal under `core/` outside `core/model/purpose.py`.

## Invariants

- `core/` names no game. A Heroes III name, code, mask character or option key in `core/`
  is a bug in the adapter boundary.
- A step gets objects from the `Catalog` it is handed and statistics from the priors it is
  handed. It reaches no module global for either.
- No test patches a module global. A test that needs different inputs passes them in.
- MapState holds grid facts only. A renderer needing a value reads it from the registry.
- One owner per fact. A second copy of a constant or a decoder is a bug.
- Runtime never mines and never writes a cache. A missing cache is an error naming the command.
- A producer provides a value once. Consumers `require` it. No consumer calls `get_or_create`.
- A directory holds one kind of thing.
- Importing a module reads no file.

## Where new code goes

Ask these in order and stop at the first yes.

1. Does it name something from Heroes III or VCMI: an object, an animation, a type, a mask
   character, a terrain code, a tile picture, an option key, a file format? `vcmi/`.
2. Is it a question the generator asks about objects? A method on `Catalog` in core terms,
   implemented in `vcmi/catalog/`. If VCMI cannot answer it, extend the tables. Never read
   it off the corpus.
3. Is it a concept generation reasons with: a purpose, a terrain property, a footprint, a
   reward? `core/model/`.
4. Does it count something across the corpus maps? The miner goes in `corpus/mine/`, the
   loader in `corpus/`, the value type in `core/priors/`, the cache in `data/pp/`, and the
   rebuild in `cli mine-stats`.
5. Does it compute over tiles alone, with no objects? `core/grid/`.
6. Does it decide something about the whole map before objects land: zones, entrances,
   borders, player zones? `core/planning/`.
7. Does it decide whether one object may stand on one tile, or pick its kind?
   `core/placement/`.
8. Is it used by exactly one step? That step's package.
9. Is it a value one step hands to a later step? A dataclass in the producer's `result.py`.
10. Does it write an output from a finished map? `renderers/`, and `vcmi/export.py` for the
    translation into VCMI's shape.
11. Is it a command a person runs? `cli/`.

Code two steps share goes one layer down, in `core/placement/`, `core/planning/` or
`core/grid/`. It never goes in one step for the other to import.

### A function or an object

The questions above say where code goes. These rules say what shape it takes there. Each
names the `code-structure` rule whose trigger a reviewer greps for.

- A value is a frozen dataclass: a result, a zone plan, a prior, a payload, a gate.
- A decision is a function over values. It takes the rng it draws from as a parameter and
  returns what it decided. A test calls it with a few literal tiles and no pipeline.
- A class earns its place four ways. It is a port with a second implementation, like
  `Catalog`. It is the only writer of state with an invariant, like `MapState.add_objs` or
  `CoverIndex`. It composes uniformly, like `PipelineStep`. Or it is an index built once that
  answers questions about its own data. Grouping functions alone earns nothing (rule 1.4).
- An index never changes after it is built. A later stage that must write goes through the
  owner of the invariant, and the owner gives the undo: `cover.mark()`, `cover.claim(cells)`,
  `cover.rollback(mark)` (rules 1.7 and 4.3).
- A function takes the fields it reads, not the container holding them. `zone_fronts`
  takes the zone label grid, not every zone record and an id (rule 1.8).
- A step's `run` reads, calls and writes. A loop inside it that chooses tiles, zones or
  objects is a function not yet moved to the step's package.
- An environment fact reaches code as a parameter. `cli/settings.py` resolves the VCMI
  install, the platform and every environment variable once. Nothing below `cli` reads
  `os.environ`, branches on `sys.platform`, or names a home directory (rule 4.1).
- A path under the program root has one owner, the module that reads that file (rule 2.7).

## Oracle

`make golden` runs `vcmi_mapgen/golden_test.py`. It generates (seed 1, size 48) and
(seed 3, size 72, subterrain) and compares a sha256 of the exported terrain tile strings,
the sorted exported objects, gate_blk and player_towns against `data/golden.json`. Both maps were measured
repeat-equal on 2026-09-27. One run costs about 2.2 minutes today: 52 s for the first map,
78 s for the second. `s24a` removes the corpus rebuild right after `s00`, so every slice
after it should run the oracle in well under a minute.

The object hash is taken over the objects as `vcmi/export.py` writes them: type, subtype,
animation, mask, options and position. `s29` and `s30` reshape `PlacedObject`. The export
stays the same, so the hash stays the same. Until `vcmi/export.py` exists, `s00` hashes the
objects as `renderers/vmap.py` writes them.

Every slice except the two marked behaviour must leave `data/golden.json` unchanged. `s33`
is marked "same" on a prediction. If its golden moves, it leaves its place and runs after
`s25` as a third behaviour slice.
A behaviour slice re-records it with `GOLDEN_UPDATE=1`, passes `make sweep`, and gets a
rendered-diff review before commit.

## Slices

Order: oracle, corpus cache, dead code, the core move, settings, other moves, the core
vocabulary and the port, splits, tidies, rewrites, behaviour last. `plan.json` holds each
slice's file list. The "After" column names the slice each one needs. Only `s15` and `s16`
run side by side. Every other pair shares a file, most often a hand-written doc or a step
file both edit, so the order is a chain.

Every slice runs `make check` and `make golden`. The table lists the checks it adds.

| Slice | After | Goal | Added checks | Map |
|-------|-------|------|--------------|-----|
| s00-oracle | | Golden oracle, import-linter, checker config | `data/golden.json` exists | same |
| s24a-cache | s00 | `cli.py mine-stats` writes every corpus cache, including new Markov and tiler files; `generate` only reads them | no corpus map loads and no `data/pp/` writes during `generate`; a missing cache errors naming `mine-stats`; generate under 20 s | same |
| s01-dead | s24a | Delete code with no production caller | `kit/reachability.py` gone; 7 dead defs gone | same |
| s02-formats | s01 | File formats under `vcmi/formats/` | no `kit.vmap`, `kit.lod`, `h3m` imports | same |
| s03-cli | s02 | `cli/` is the only entry point; one step list | `cli.py`, `extract_vmap.py`, `corpus_match.py` gone; a terrain-only run works | same |
| s36-core | s03 | `models/`, `pipeline.py` and `steps/` move under `core/` whole | no `vcmi_mapgen.steps`, `vcmi_mapgen.models` or `vcmi_mapgen.pipeline` import; a terrain-only run works | same |
| s32-settings | s36 | Environment facts resolved once in `cli/settings.py`; `vcmi/install.py` finds the install from the environment it is handed | no `os.environ`, `sys.platform`, `expanduser`, `/home/`, `~/` or flatpak path literal outside `cli/settings.py` and `vcmi/install.py`; no `LOD_DIR` or `_BASES` at module scope; `render-sprites` with no install raises naming `VCMI_HOME` | same |
| s04-grid | s32 | Pure grid algorithms under `core/grid/` | segmentation files and `islands.py` gone | same |
| s05-catalog-tables | s04 | Ontology tables and queries under `vcmi/catalog/`; tables in JSON | `--regen` reproduces the JSON exactly; `ontology.py` gone | same |
| s06-terrain | s05 | `Terrain` in `core/model/`; codes and prefixes in `vcmi/terrain.py` | no `WATER = 8`, `WATER, ROCK = 8, 9`, `TNAME`, `TCODE`; no terrain names compared as strings in steps | same, overlays fix rock |
| s07-purpose | s06 | `Purpose` and `Resource` enums | no `objlib.json` reads; no purpose string outside `purpose.py` | same |
| s28-catalog-port | s07 | `Catalog` port in core; `VcmiCatalog` in `vcmi/`; every lookup goes through the instance | no import of `vcmi` or `ontology` from steps, placement, planning or pipeline; the `Ontology` class gone; one step test runs on a fake catalog | same |
| s29-footprint | s28 | `Footprint` replaces mask strings in the core | no `Mask` type under `core/`; mask charset only in `vcmi/` | same |
| s08-corpus | s29 | One `.vmap` loader in `vcmi/load.py`; corpus loading to `corpus/`; footprints to `core/placement/` | `kit/objects.py`, `readers/`, `FaithfulMap`, `_adapt` gone; every `.vmap` read goes through `load_map` or the format reader | same |
| s09-placement | s08 | `core/placement/` package | `steps/placement.py`, `validate.py`, `steps/gate/`, `site.py` gone | same |
| s10-planning | s09 | `core/planning/` package; one zone record | `kit/topology.py`, `steps/zone_plan.py`, `zone_record.py` gone | same |
| s34-gates | s10 | One `Gate(rep, band)` value in `core/planning/`; `zone_gates` and `zone_gate_bands` share one front walk; `zone_fronts` takes the zone label grid | the centroid and antipodal-pair code appears once; no function in `core/planning/` rebuilds a tile owner map from every zone | same |
| s11-results | s34 | Results in `result.py` | no `*Result` class elsewhere | same |
| s12-segment-fold | s11 | terrain_gen provides `Segmentation` | `steps/segment/` gone; no `map_state.zones` | same |
| s33-claims | s12 | The cover index owns claims with `mark`, `claim` and `rollback`; `ZoneRecord.used` goes | no `.used` write; `_Snapshot` and `_restore` gone from `gated/placer.py`; treasure claims a tile once | same, predicted |
| s13-gameplay | s33 | Split `mines.py` and `draw.py` | `mines.py` gone; one `ECONOMY` | same |
| s14-loot | s13 | Split `caches.py`; one reward builder | `caches.py`, `_pandora_reward` gone | same |
| s15-portal | s14 | Split portal geometry | `portal/geometry.py` gone | same |
| s16-vegetation | s14 | Vegetation mining to corpus | border stops importing vegetation | same |
| s17-terrain-gen | s15, s16 | Split terrain_gen; miners to `corpus/mine` | `macro_topo.py`, `markov.py` gone | same |
| s18-crossings | s17 | Rename border_seal | `border_seal.py` gone | same |
| s19-renderers | s18 | Split sprites and vmap; `vcmi/export.py` and `vcmi/players.py` | `renderers/vmap.py` holds no translation | same |
| s20-object-roles | s19 | Steps ask the catalog for guards, random artifacts, portals, quest givers and graded draws | no `"av[a-z0-9]+"` literal, `RND_MON`, `ART_BY_LVL`, `PORTAL_ANIMS` or `"seerHut"` under `core/` | same |
| s30-payloads | s20 | `Guard`, `Reward`, `Quest` replace VCMI option dictionaries; `vcmi/export.py` translates | `PlacedObject` has no `options`, `type`, `subtype`, `animation`; no option key literal under `core/` | same |
| s31-tile-art | s30 | Tile art leaves the core. terrain_gen writes one `Terrain` grid; export and the PNG renderer tile it | MapState has no `surfs` or `cells`; `TerrainGrids` has no `grids`; no `Cell` under `core/`; `kit/tiling.py` gone | same |
| s21-one-bfs | s31 | One BFS family | copies routed to `core/grid/reach.py` | same |
| s22-level-param | s21 | Samplers take the level | no `.level = 1` retags | same |
| s23-workspace | s22 | Typed results replace the workspace | no workspace names, no `get_or_create` | same |
| s35-thin-run | s23 | Each step's `run` reads, calls and writes; the choosing loops move to the step's package | vegetation, scatter, border, portal and terrain_gen `run` under 30 lines; one test per moved function calls it without a pipeline | same |
| s24b-priors | s35 | Priors are values `cli` loads once and passes to step constructors | no step reads `data/pp/`; no test patches a corpus statistic | same |
| s25-contracts | s24b | Import contracts and the three grep checks on; `kit/` gone | `lint-imports` passes; the grep checks find nothing; `project_root()` has one caller, `cli/settings.py` | same |
| s26-fill-one-pass | s25 | Treasure fill as one pass | `make sweep` | changes |
| s27-artifact-tier | s26 | One top random-artifact tier | `make sweep` | changes |

`s34` must keep two orders that differ today. `zone_gates` returns neighbours in the order
`zone_fronts` found them, and `zone_gate_bands` sorts them by zone id. A shared walk that
picks one order moves the golden.

`s33` has one known double write. `treasure/fill.py` adds a tile to `used` right after
`cover.try_add` claimed it. Whether `used` ever holds a tile the cover index does not is
the reading `make golden` gives.

`s35` comes after `s23` because most of what `run` does today is read and write workspace
fields. The 30-line bar is hardcoded, set against today's lengths: vegetation 74, scatter
50, border 45, portal 43, terrain_gen 42, and gated 27 as the longest that passes today.

`s28` is where the testing gain lands. It routes the 59 module calls and the 3 instance
calls through one `Catalog` object. It touches the 28 core modules that mention the
ontology today, so it runs before the splits, while those modules are still where
`plan.json` finds them.

Every rename updates the hand-written docs in the same slice. The farrier-generated
`AGENTS.md` files and the skill sources live in agent-library. Each slice greps them for old
names, edits them there and runs `make agent-install`. The `vcmi-mapgen` skill's rule
"`ontology.py` is the single source of truth for objects" becomes "`Catalog` is the only
way the core learns about objects, and `vcmi/catalog/` is its production source".

## Decisions left open

- **The top random-artifact tier.** Fill uses `avarnd4`. Caches and mines use `avarand`.
  `s20` keeps both behind `catalog.random_artifact`. `s27` unifies them, which changes maps.

## Debt kept out of scope

- `h3m.py` (1,202 lines) moves whole. It mirrors the C++ reader and splitting it buys little.
- `gate_blk` lives on MapState and on `GateResult`.
- BFS copies that change the map when unified stay, and `s21` records each one here.

## Found while surveying

- Overlays decode rock wrong. `renderers/overlays/_tiles.py` maps the prefix `ro`, but VCMI
  writes rock as `rc`. Rock decodes as dirt, so the passable-tile overlay treats rock as land
  and tints it as dirt. The codes `hl` and `wa` map to 10 and 11, which are not terrains.
  This affects debug overlays only, and the generated map is unaffected. It can be fixed
  now, independently of this plan. `s06` removes the cause by giving the prefixes one table
  in `vcmi/terrain.py`.
- `kit/vcmi_config.py` builds its search paths from `VCMI_HOME` at import time, and
  `kit/lod.py` does the same for `LOD_DIR`. Importing either reads the environment and lists
  directories. `kit/paths.py` falls back to the first candidate when no VCMI install exists,
  so a missing install surfaces later as a missing file. `s32` removes both.
- `ROOT = project_root()` is recomputed in 11 modules. Each copy goes with the module that
  reads the file, and `s25` checks one caller is left.

## Evidence

- Corpus rebuild time, measured 2026-09-27 on the i7-4790. Timed alone, `markov.learn(0)`
  plus `learn4(0)` took 27.6 s and `_learn_terrain_tiler()` took 19.9 s, 47.5 s together.
  One pass of `load_faithful` over the 159 maps took 14.9 s. A profiled
  `generate --seed 1 --size 48 --renderers vmap --overlays none` spent 86.5 s of 100.3 s
  in the three learners, across 477 `load_faithful` calls. The profiler inflates both
  numbers, and the share is 86%. The golden runs took 52 s and 78 s without a profiler.
- Game names in the core, counted 2026-09-28 over the 47 non-test modules under `steps/`,
  plus `pipeline.py` and `validate.py`: 168 uses of 25 distinct upper-case purpose strings,
  the most frequent being `"GUARD"` (26), `"RESOURCE_PILE"` (22), `"TOWN"`, `"MINE"` and
  `"REWARD_PICKUP"` (16 each); 54 VCMI animation literals matching `"av[a-z0-9]+"`; 7 VCMI
  type literals (`"shipyard"`, `"pandoraBox"`, `"seerHut"`); VCMI option dictionaries
  built in 9 modules; `WATER = 8` or `WATER, ROCK` defined in 6 modules; 28 of the 47
  modules mention the ontology.
- Catalog use: about 62 call sites. 59 call module functions directly, led by `pool` (18)
  and `identity_of` (17). 3 in production call the `Ontology` instance: `allowed_on` in
  `TerrainGate`, `vmap_mask_of` in the vmap writer and `pool` in water. No test substitutes
  the instance.
- Test patches of module globals: `steps/gate/gates_test.py` patches `mine_gate_stats` in
  three tests; `kit/objects_test.py` patches `faithful_path` twice.
- Inventory: 131 tracked Python files: 20 keep, 59 move, 39 split, 8 merge, 5 delete. The
  earlier layering had 54 keep and 28 move. The difference is `s36`, which moves `models/`,
  `pipeline.py` and `steps/` under `core/`.
