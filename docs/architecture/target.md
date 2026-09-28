# Target architecture (draft)

Status: draft, 2026-09-27. Nothing here is approved. `plan.json` beside this file holds the
fate of every Python source and the ordered slices that get there.

This draft was drawn on the working tree while the gameplay-after-vegetation work was still
uncommitted (37 files). Slice `s00-oracle` waits until that work lands. Regenerate the plan
then, because paths and importers may have moved.

## What the generator is

One seeded pipeline turns a seed, a size and a subterrain flag into a playable `.vmap`. The
same inputs always give the same map. The corpus of 159 real maps supplies spatial
statistics. The ontology supplies object identity.

## Core models and the facts they own

| Fact | Owner | Notes |
|------|-------|-------|
| Tile terrain and tile art | `models.MapState.surfs`, `.cells` | Dual representation. Named debt, out of scope. |
| Placed objects | `models.MapState.objs` | Additive: a step appends, never moves or removes. |
| Gate blocking tiles | `models.MapState.gate_blk` | Also held by `GateResult`. Named debt, out of scope. |
| Player towns | `models.MapState.player_towns` | |
| Zones and tile-to-zone | `Segmentation`, provided by terrain_gen | Leaves MapState in `s12`. |
| Terrain codes and names | `models.terrain.Terrain` | Replaces 9 copies of `WATER, ROCK = 8, 9` and 4 name tables. |
| Object purpose | `models.purpose.Purpose` via `ontology` | Stops reading `objlib.json`. |
| Object identity, mask, category, tier, level | `ontology` | Tables load from `data/ontology/*.json`. |
| Corpus statistics | `corpus` loaders over `data/` caches | Mined only by `cli`. |
| Cross-step values | typed dataclasses in `steps/<name>/result.py` | Replace `PlacementWorkspace`. |

## Sources of truth

- The step list: `cli/steps.py` `build_steps`. `corpus_match` uses it too.
- Object facts: `ontology`. The corpus never decides identity, mask or category.
- Statistics: the files under `data/`. Runtime reads them. Only `cli` subcommands write them.
- Map equality: `data/golden.json`, checked by `make golden`.

## Target tree

Each line names the one kind of thing the directory holds.

```
vcmi_mapgen/
  cli/          entry points: generate, render-ontology, extract-vmap, corpus-match, audit, miners
  pipeline.py   the engine: PipelineStep, Pipeline, ProviderRegistry
  steps/        one package per pipeline step; step.py plus result.py plus step-private helpers
  renderers/    png, sprites (compositing), vmap, vmap_players, palette, overlays, ontology_render
  planning/     whole-map plans: zone_plan, zone_index, entrances, borders, player_zones
  placement/    placing one object legally: footprint, cells, rules, guards, identity, intensity,
                rewards, site, place, scatter
  corpus/       loaders over data/ caches; corpus/mine/ holds the miners
  grid/         pure grid algorithms: geometry, noise, segment, components, reach, paths, pockets
  ontology/     object facts: tables, objects, decor, graded, loot, regen
  formats/      file formats: vmap/, h3m, lod, defs, json_value, vcmi_config, paths
  models/       value types and MapState: terrain, purpose, objects, map_state
```

`kit/` and `readers/` disappear. `steps/segment/` folds into `steps/terrain_gen/`.
`steps/gate/` holds no step and splits into corpus, placement and terrain_gen.

## Import contract

Checked by import-linter from `s25-contracts`. Top imports bottom, never the reverse.

1. `cli`
2. `steps` | `renderers`
3. `pipeline`
4. `planning`
5. `placement`
6. `corpus`
7. `grid`
8. `ontology`
9. `formats`
10. `models`

- `steps.*` are independent. The one allowed crossing is a step importing another step's `result`.
- `corpus.mine` is forbidden to `steps`, `placement`, `planning` and `pipeline`.

## Invariants

- MapState holds grid facts only. A renderer needing a value reads it from the registry.
- One owner per fact. A second copy of a constant or a decoder is a bug.
- Runtime never mines and never writes a cache. A missing cache is an error naming the command.
- A producer provides a value once. Consumers `require` it. No consumer calls `get_or_create`.
- A directory holds one kind of thing.
- Importing a module reads no file.

## Oracle

`make golden` runs `vcmi_mapgen/golden_test.py`. It generates (seed 1, size 48) and
(seed 3, size 72, subterrain) and compares a sha256 of surfs, cells, sorted objs, gate_blk
and player_towns against `data/golden.json`. Both maps were measured repeat-equal on
2026-09-27. One run costs about 2.2 minutes: 52 s for the first map, 78 s for the second.

Every slice except the two marked behaviour must leave `data/golden.json` unchanged.
A behaviour slice re-records it with `GOLDEN_UPDATE=1`, passes `make sweep`, and gets a
rendered-diff review before commit.

## Slice order

Oracle, dead code, moves, splits, rewrites, behaviour last. The overlap of touched files
makes the order almost serial: 24 waves for 28 slices. Three waves allow two or three
slices in parallel. `plan.json` holds each slice's goal, touches, dependencies, checks and
rules. Its touches name paths as they are today. A path moved by an earlier slice lives at
its fate's `to`.

Every rename updates the hand-written docs in the same slice. The farrier-generated
`AGENTS.md` files and the skill sources live in agent-library. Each slice greps them for old
names, edits them there and runs `make agent-install`.

## Decisions left open

- The `Ontology` facade has no fields and 15 modules bypass it. Delete it and call module
  functions, or give it state and route every caller through it. The plan keeps it until
  this is taken.
- The top random-artifact tier disagrees: fill uses `avarnd4`, caches and mines use
  `avarand`. `s20` preserves both. `s27` unifies them and changes maps.

## Debt kept out of scope

- `h3m.py` (1202 lines) moves whole. It mirrors the C++ reader and splitting it buys little.
- `surfs` and `cells` are two views of one grid.
- `gate_blk` lives on MapState and on `GateResult`.
- BFS copies that change the map when unified stay, and `s21` records each one here.

## Found while surveying

- Overlays decode rock wrong. `renderers/overlays/_tiles.py` maps the prefix `ro`, but VCMI
  writes rock as `rc`. Rock decodes as dirt, so the passable-tile overlay treats rock as land
  and tints it as dirt. The codes `hl` and `wa` map to 10 and 11, which are not terrains.
  This affects debug overlays only, and the generated map is unaffected. It can be fixed
  now, independently of this plan.

## Inventory

131 Python files: 54 keep, 28 move, 36 split, 7 merge, 6 delete. `plan.json` lists each.
