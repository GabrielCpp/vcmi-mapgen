---
name: vcmi-mapgen
description: "VCMI map-generator repo root — what the project is, uv tooling, the package layout, and how to run the CLI / pipelines / tests. Load first for any work in this repo."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards, entrypoint]
---

# VCMI map-generator — repository root

A **learned procedural map generator** for VCMI / Heroes 3 maps: a corpus-fitted
marked-point-process pipeline synthesizes terrain, zones, gameplay objects, vegetation,
loot and repairs into a playable map (`cli.py generate`). Corpus statistics (`data/`,
`maps_vmap/`) are learned once from 159 real `.h3m` maps via `extract_vmap.py` and read
back by the generator's individual steps (mine/dwelling densities, vegetation
point-process parameters, macro-terrain style) — there is no separate rebuild/replay
engine; the corpus only ever informs *statistics*, never map content directly.

Load `vcmi-mapgen-maps` for the domain details (formats, segmentation, rendering).
Load `vcmi-mapgen-pipeline` before adding/changing a pipeline step or a `cli.py`
subcommand (the step contract, `MapState`, `ProviderRegistry`).

## Tooling — this is a `uv` Python project

- Run **everything** through uv as a module: `uv run python -m vcmi_mapgen.<module> [...]`.
  Dependencies (`pyproject.toml`): Pillow + numpy; everything else is stdlib. Never
  `pip install`; never assume a system interpreter — `uv run` resolves the env.
- Determinism: replay is integer-only; the terrain generator is seeded. Don't introduce
  `random`/time without a seed.

## Where things are

- **`vcmi_mapgen/`** — the package (run modules with `python -m vcmi_mapgen.<name>`):
  - `cli.py` — the CLI (`generate` / `render-ontology`), a thin layer over `pipeline.py`.
  - `pipeline.py` — `MapState` (the narrow, render-only view of a finished map),
    the Gameplay/Vegetation/Pickup/Repair collaboration workspaces, the `ProviderRegistry`
    (typed, memoized cross-step values), and the `PipelineStep`/`Pipeline` contract every
    step is built from. See `vcmi-mapgen-pipeline` for the contract itself and
    `steps/AGENTS.md` for what a step must do.
  - `steps/` — one subpackage per step: `terrain_gen/segment/gate/gameplay/vegetation/
    pickup/repair`.
  - `terrain_segment.py` — same-terrain flood-fill segmentation + interior-depth features.
  - `kit/objects.py`, `ontology.py` — corpus loader, object identity, purpose.
  - `kit/vmap/{reader,writer}.py` — the full `.vmap` reader/writer.
  - `renderers/sprites.py` — editor-quality 32px H3 sprite rendering (decodes DEF fmt
    0/1/2/3); `renderers/png.py` — schematic PNGs; `renderers/vmap.py` — playable `.vmap`
    export (`VmapRenderer` builds the `VmapDocument` directly from a finished `MapState`);
    `renderers/overlays/` — debug overlay layers (zone/blocking/pocket/...), only
    `generate` selects these from the CLI; `renderers/ontology_render.py` — the
    `render-ontology` catalog dump (a documentation tool, not part of the pipeline).
  - `steps/terrain_gen/markov.py` — the terrain generator (Markov chain learned from
    the corpus), consumed by `steps/terrain_gen/macro_topo.py`.
  - `h3m.py`, `vcmi_ids.py`, `extract_vmap.py` — `.h3m` → `.vmap` corpus-extraction pipeline.
  - `renderers/sprites_test.py` — rendering-engine reliability tests.
- **`maps/`** — the `.h3m` corpus (159 maps), the source data.
- **`maps_vmap/`** — one real `.vmap` per corpus map (the engine's input; regenerable from
  `maps/` via `extract_vmap.py`).
- **`data/`** — corpus-derived priors (`objlib.json`, `pp/*.json` — macro/gameplay/vegetation
  statistics) and static VCMI-derived reference tables (`objclass_names.json` — the raw
  MapObjectID enum, feeding `ontology.py --regen`; `vmap_header_template.json`). Static
  VCMI/corpus-derived JSON lives here, never loose beside the `.py` sources — if you add a
  reference table, it goes in `data/`.
- **`out/`** — transient outputs (templates, features, renders); **gitignored**.
- **`vcmi-h3m-format-reference/`** — verbatim VCMI C++ sources documenting the `.h3m` format
  (see `docs/vcmi-h3m-format-reference.md`).

## How to run

```bash
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72    # procedural generator
uv run python -m vcmi_mapgen.extract_vmap                      # regenerate maps_vmap/ from maps/
uv run pytest                                                  # rendering-engine reliability tests
```

Editor-quality rendering reads the H3 sprite LOD files from a local VCMI install
(`~/.var/app/eu.vcmi.VCMI/data/vcmi/Data`); the rendering tests skip when those are absent.

## Rules

- **`ontology.py` is the SINGLE SOURCE OF TRUTH for objects, from tile placement through map
  rendering.** Object identity, footprint mask, terrain coupling and decoration category for the
  *generation* pipeline come from `ontology.py` — the hardcoded `TAXONOMY` + `LEAF_META` literals,
  re-derived from the authoritative editor table `objects.txt` via `python -m vcmi_mapgen.ontology
  --regen`. Use its accessors (`identity_of`, `mask_of`, `is_blocking`, `terrains_of`, `decor_pool`,
  `veg_categories`, `category_of`, `decode_identity`, `category_terrain_matrix`). When something the
  pipeline needs is missing, **extend the ontology** (parse it from `objects.txt` and regenerate) —
  do NOT reach into the corpus (`data/objlib.json` / `obj_resolve._OBJLIB`, faithful maps, or a
  `veg_data` corpus scan) for object identity/mask/category. The corpus may still inform spatial
  *statistics* (density/openness/frequency weights), never identity. `veg_data`'s category functions
  are thin ontology adapters.
- **Every pipeline step must write onto `MapState`** — there are no ctx-only steps. Anything
  else a step produces for a later step goes through the `ProviderRegistry` as a typed
  dataclass, never a raw string-keyed dict entry. See `steps/AGENTS.md` for the full
  contract.
- Generated artifacts live in `out/` (gitignored). Do **NOT** copy them into the VCMI
  `Maps/` folder.
- Treat `CLAUDE.md` and `.claude/` as generated adapter outputs — edit the canonical skill
  sources and re-run `make agent-install`, never hand-edit them.
