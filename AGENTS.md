# VCMI map-generator: repository root

A procedural map generator for VCMI, the open-source Heroes of Might and Magic III
engine. It learns its statistics from a corpus of 159 real maps and generates playable
`.vmap` maps: terrain, towns, mines, dwellings, guarded treasure and vegetation. The same
seed always gives the same map.

Load `vcmi-mapgen-maps` for the domain: formats, object identity, segmentation and
rendering. Load `vcmi-mapgen-pipeline` before adding or changing a pipeline step or a
`cli/` subcommand.

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

- **`vcmi_mapgen/`**, the package, in four layers:
  - `cli/`: the CLI. `__main__.py` holds the subcommands, `generate.py` runs one map and
    `steps.py` `build_steps` builds the pipeline. The corpus and report tools sit beside
    them: `extract_vmap.py`, `corpus_match.py`, `mine_stats.py`, `audit.py` and
    `readings.py`, which prints the map-math 8 readings per terrain model beside the
    corpus spread, `effort_report.py`, which prints each gated place's hero-days,
    band and top prize, and `patch_report.py`, which prints how the corpus and
    generated maps dress their small enclosed patches.
  - `core/`: the pure generator. It imports nothing from `vcmi/`, `corpus/` or `renderers/`.
    - `pipeline.py`: `PipelineStep`, `Pipeline` and `ProviderRegistry`.
    - `catalog.py`: the `Catalog` port, the only way the core learns about objects.
    - `model/`: `MapState`, the map's tile grid and object list, its `CoverIndex` that
      owns claims, plus the plain data types `PlacedObject`, `Cell`, `Tile` and `Zone`.
    - `steps/`: one subpackage per pipeline step, each with a `step.py` and a `result.py`
      for the values it publishes.
    - `grid/`: pure grid algorithms: segmentation (`segment.py`), components, geodesic
      paths, pockets, edge distance and noise.
    - `placement/`: where an object stands: footprint cells (`footprint.py`), the ground
      rule that every solid cell stands on terrain its identity allows (`ground.py`),
      guards, sites, `place_one` and scatter.
    - `planning/`: the zone plan `VegetationStep` starts from (`zone_plan.py`), the entrance
      geometry (`entrances.py`), the one `ZoneRecord` per zone (`zone_index.py`) and the
      content intent per place, its role, hop from home, reward and guard level
      (`content.py`), and the guard level in front of each prize in a cut-off place
      (`guarding.py`).
    - `reading/`: the place reader both sides share. It infers places from a corpus or a
      generated map (`ground.py`, `places.py`), and measures them: borders, palettes
      (`palette.py`), content by role and hop (`content.py`), object value and guard
      level (`value.py`), roads, and one map's reading vector with the switch rule
      (`vector.py`, `verdict.py`). It also routes a hero over a map (`routes.py`) and
      prices each tile in hero-days from the nearest home (`effort.py`). It reads the
      small enclosed patches with their cover and content (`patches.py`), and counts the
      objects closed on both flanks (`flanks.py`) and the objects that sit snug for
      their size (`snug.py`). It gives each gameplay object its
      family and the days from the nearest home to reach it (`families.py`).
    - `steps/terrain_gen/`: the terrain models. `places` is the default: it lays out a
      place graph and paints each place. `markov` paints terrain from corpus transitions
      and floods it into places. `palette.py` groups the places of the places model into
      palette regions, one dominant terrain each.
    - `priors/`: the corpus priors as frozen values.
  - `vcmi/`: everything that knows VCMI. `catalog/` is `VcmiCatalog`, the production
    `Catalog`, with its tables in `data/catalog/`. `content/` resolves the enabled mods
    and the banned names the catalog filters by. It also reads each enabled mod's
    objects and sprites, and the header's list of the mods a map needs. `formats/` reads and writes `.h3m`,
    `.vmap`, LOD and DEF files. `tiles.py` autotiles terrain, `export.py` and `players.py`
    build a playable map, `load.py` `load_map` reads a `.vmap` back into a `MapState`
    with its roads, and
    `config.py` finds the local VCMI install.
  - `corpus/`: the corpus loader (`maps.py`), the priors loader (`priors.py`), the
    corpus-versus-generated tally (`match.py`) and the miners in `mine/`.
  - `renderers/`: `PngRenderer` with real H3 sprites (`png.py`, `sprites.py`), the
    terrain colours (`palette.py`), `VmapRenderer` for playable `.vmap` export
    (`vmap.py`), the debug overlays (`overlays/`), and the `render-ontology` catalog
    (`ontology_render.py`).
- **`data/`**: every map and data file the project keeps. `corpus/h3m/` holds the
  `.h3m` corpus, 159 maps. `corpus/vmap/` holds one `.vmap` per corpus map, regenerated
  from `corpus/h3m/` by `extract-vmap`. `catalog/*.json` holds the VCMI object tables,
  rebuilt by `regen-ontology`. `pp/*.json` holds the corpus-derived priors and `golden.json`
  the golden map hashes. `pp/place_stats*.json` holds the place statistics, with the
  place content and the road statistics the places model draws from. The fixed `.vmap`
  header lives with its reader, in `vcmi/formats/vmap/header_template.json`.
- **`out/`**: transient renders and maps. It is gitignored.
- **`vcmi-h3m-format-reference/`**: verbatim VCMI C++ sources for the `.h3m` format,
  described in `docs/vcmi-h3m-format-reference.md`.

## How to run

```bash
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72 --subterrain --stop-after vegetation
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72 --terrain markov --stop-after roads
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72 --mods hota --ban pandoraBox angel
uv run python -m vcmi_mapgen.cli render-vegetation --seeds 1 2 3 --vegetation field
uv run python -m vcmi_mapgen.cli render-ontology
uv run python -m vcmi_mapgen.cli regen-ontology
uv run python -m vcmi_mapgen.cli audit
uv run python -m vcmi_mapgen.cli extract-vmap
uv run python -m vcmi_mapgen.cli corpus-match --seeds 1 2 3 --size 48
uv run python -m vcmi_mapgen.cli readings --seeds 1 2 3 4 5 6 7 8 9 10 --size 72
uv run python -m vcmi_mapgen.cli effort-report --seeds 1 2 3 4 5 6 7 8 9 10 --size 72
uv run python -m vcmi_mapgen.cli patch-report --seeds 1 2 3 4 5 6 7 8 9 10 --size 72
make check
make golden
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
  decoration category come from `data/catalog/taxonomy.json` and
  `data/catalog/leaf_meta.json`. `python -m vcmi_mapgen.cli regen-ontology` re-derives
  them from the editor table `objects.txt`. When the pipeline needs something the
  catalog lacks, add a `Catalog` method and extend the ontology behind it. The corpus may inform spatial statistics such as
  density, openness and frequency weights. It never decides object identity, mask or
  category.
- Generated artifacts live in `out/`. Do not copy them into the VCMI `Maps/` folder.
- The root and `vcmi_mapgen/` `AGENTS.md` and everything under `.claude/` are generated
  by farrier. Edit the library source that `farrier source <file>` prints, then
  run `make agent-install`. `core/steps/AGENTS.md` and `core/model/AGENTS.md` are hand-written and
  edited in place. `[code-review]` in `.agent-checks.toml` configures the `code-review`
  reviewer.
- **A rename or deletion updates the docs in the same change.** When you rename, move or
  delete a module, class, function or CLI subcommand, grep for the old name in the
  `AGENTS.md` files, `README.md`, `docs/architecture.md` and the library skill sources.
  Fix every hit before committing. These files load into every session, so a stale name
  sends the next change toward code that no longer exists.
