# VCMI map-generator: repository root

A procedural map generator for VCMI, the open-source Heroes of Might and Magic III
engine. It learns its statistics from a corpus of 159 real maps and generates playable
`.vmap` maps: terrain, towns, mines, dwellings, guarded treasure and vegetation. The same
seed always gives the same map.

Load `vcmi-mapgen-maps` for the domain: formats, object identity, segmentation and
rendering. Load `vcmi-mapgen-pipeline` before adding or changing a pipeline step or a
`cli.py` subcommand.

## Tooling: this is a `uv` Python project

- Run everything through uv as a module: `uv run python -m vcmi_mapgen.<module> [...]`.
  Never `pip install`, and never assume a system interpreter.
- `make check` is the gate: `make lint` (ruff check, ruff format, basedpyright in
  `all` mode) then `make test` (pytest). CI runs `make check`. The pre-commit hook runs
  only `make lint`, so run `make test` yourself before committing a behavior change.
- `make sweep` runs the slow whole-pipeline seed sweep.
- Determinism: every random draw comes from a seeded `random.Random`. Never introduce
  unseeded randomness or time.

## Where things are

- **`vcmi_mapgen/`**, the package:
  - `cli.py`: the CLI, with `generate` and `render-ontology`. It builds the pipeline.
  - `pipeline.py`: `PipelineStep`, `Pipeline`, `ProviderRegistry` and the
    `PlacementWorkspace` the placement steps share.
  - `models/`: `MapState`, the map's tile grid and object list, plus the plain data
    types `PlacedObject`, `Cell`, `Tile` and the pocket and zone records.
  - `steps/`: one subpackage per pipeline step, each with a `step.py`. `steps/gate/`
    holds no step. It keeps the gate statistics and footprint helpers. `steps/placement.py`
    and `steps/zone_index.py` hold helpers several placement steps share.
    `steps/zone_plan.py` builds the zone entrances, the walkable web and the sea plan that
    `VegetationStep` starts from.
  - `core/grid/`: pure grid algorithms: segmentation (`segment.py`), components,
    geodesic paths, pockets, edge distance and noise.
  - `core/placement/`: footprint cell expansion (`footprint.py`).
  - `kit/`: step-independent helpers. It covers topology and autotiling (`tiling.py`).
  - `corpus/`: the corpus loader (`maps.py`) and the corpus-versus-generated tally.
  - `vcmi/catalog/`: object identity, footprints, terrain coupling and decoration
    category, read from the tables in `data/ontology/`.
  - `renderers/`: `PngRenderer` with real H3 sprites (`png.py`, `sprites.py`),
    `VmapRenderer` for playable `.vmap` export (`vmap.py`), the debug overlays
    (`overlays/`), and the `render-ontology` catalog (`ontology_render.py`).
  - `vcmi/load.py`: `load_map`, which loads a `.vmap` back into a `MapState`.
  - `validate.py`: `TerrainGate`, the terrain placement rule `MapState.add_objs` checks.
  - `h3m.py` and `extract_vmap.py`: the `.h3m` to `.vmap` corpus extraction.
  - `corpus_match.py`: a report comparing object placement in corpus and generated zones.
- **`maps/`**: the `.h3m` corpus, 159 maps.
- **`maps_vmap/`**: one `.vmap` per corpus map, regenerated from `maps/` by
  `extract_vmap`.
- **`data/`**: corpus-derived priors (`pp/*.json`) and static VCMI-derived tables
  (`objclass_names.json`, `vmap_header_template.json`, `ontology/vcmi_types.json`). Any new
  static reference table goes here, never beside the `.py` sources.
- **`out/`**: transient renders and maps. It is gitignored.
- **`vcmi-h3m-format-reference/`**: verbatim VCMI C++ sources for the `.h3m` format,
  described in `docs/vcmi-h3m-format-reference.md`.

## How to run

```bash
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72 --subterrain --stop-after vegetation
uv run python -m vcmi_mapgen.cli render-ontology
uv run python -m vcmi_mapgen.cli regen-ontology
uv run python -m vcmi_mapgen.cli audit
uv run python -m vcmi_mapgen.extract_vmap
uv run python -m vcmi_mapgen.corpus_match --seeds 1 2 3 --size 48
make check
```

Sprite rendering reads the H3 LOD files from a local VCMI install, found per OS or
through `VCMI_HOME`. The rendering tests skip when those files are absent.

## Rules

- **`Catalog` (`core/catalog.py`) is the only way the core learns about objects.**
  A step receives one `Catalog` in `run` and passes it first to every function that asks
  about an object: `identity_of`, `spec`, `allowed_on`, `candidates`, `decor`,
  `decor_category`, `decor_categories`, `mines_by_resource`, `spells`, `terrain_name`.
  No module under `core/` imports `vcmi.catalog`. `vcmi/catalog/` is the production source,
  `VcmiCatalog` in `adapter.py`. Its identity, footprint mask, terrain coupling and
  decoration category come from `data/ontology/taxonomy.json` and
  `data/ontology/leaf_meta.json`. `python -m vcmi_mapgen.cli regen-ontology` re-derives
  them from the editor table `objects.txt`. When the pipeline needs something the
  catalog lacks, add a `Catalog` method and extend the ontology behind it. The corpus may inform spatial statistics such as
  density, openness and frequency weights. It never decides object identity, mask or
  category.
- Generated artifacts live in `out/`. Do not copy them into the VCMI `Maps/` folder.
- The root and `vcmi_mapgen/` `AGENTS.md` and everything under `.claude/` are generated
  by farrier. Edit the library source that `farrier source <file>` prints, then
  run `make agent-install`. `steps/AGENTS.md` and `models/AGENTS.md` are hand-written and
  edited in place.
- **A rename or deletion updates the docs in the same change.** When you rename, move or
  delete a module, class, function or CLI subcommand, grep for the old name in the
  `AGENTS.md` files, `README.md`, `docs/architecture.md` and the library skill sources.
  Fix every hit before committing. These files load into every session, so a stale name
  sends the next change toward code that no longer exists.
