---
name: vcmi-mapgen-maps
description: "VCMI maps domain — h3m/vmap formats, object identifiers, faithful JSON, terrain segmentation, and editor-quality sprite rendering. Load when changing vcmi_mapgen/ code."
metadata:
  generated_by: farrier
  source: library/skills/projects/vcmi-mapgen/vcmi-mapgen-maps/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-maps/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, standards]
---

# VCMI maps — domain facts (formats, segmentation, rendering)

## Formats & identifiers

- `.h3m` (real maps): gzip binary, parsed by `vcmi_mapgen/h3m.py` (`parse_file` → `H3Map`
  with terrain tiles + objects; RoE/AB/SoD only). `.vmap` (editor): zip of relaxed JSON,
  read/written by `vcmi_mapgen/kit/vmap/{reader,writer}.py` (a full `VmapDocument` model —
  header players/teams/victory/defeat, every object, terrain as VCMI tile strings — with an
  `extra` catch-all so an unmodeled key still round-trips losslessly).
- **The corpus** (`maps_vmap/<name>.vmap`, loaded by `kit.objects.load_faithful`) feeds the
  generator's own priors (`data/objlib.json`, `data/pp/*.json` — mine/dwelling densities,
  vegetation point-process parameters, macro-terrain style). Regenerate from `maps/` with
  `python -m vcmi_mapgen.extract_vmap`. The engine-internal mask charset (`'X'`
  blocked-entrance vs `'A'` walk-on) is NOT read back from a `.vmap`'s `template.mask`
  (VCMI's own charset can't represent that distinction — see `kit.vmap.terrain.vcmi_mask`'s
  docstring); `load_faithful` re-derives it from `ontology.mask_of(animation)` instead,
  falling back to the file's own mask only when the ontology has no data for that animation
  at all (heroes — their per-portrait animations aren't in `objects.txt`'s catalog — where
  the fallback is safe since a hero's mask has no `'B'` cell to begin with).
- Object identity comes from VCMI's own config via `vcmi_mapgen/kit/vcmi_config.py`
  (`resolve(obj_class, obj_subid) → (type, subtype)`). Never guess subtypes. The reference
  C++ format sources are in `vcmi-h3m-format-reference/`.
- A visitable object's template needs `visitableFrom` (the 3×3 approach grid) or the editor
  warns "no visitable directions" — `renderers.vmap.VmapRenderer._build_document` sets it.
- Footprints: `kit.objects.mask_cells(mask, x, y)` expands a mask anchored at its
  bottom-right cell; `'B'` = blocking, `'A'`/`'V'` = visitable/overlay, `' '` = empty.

## Segmentation

- `terrain_segment.segment(level, subdivide=False)` → `(zones, zone_label)`: 4-conn
  flood-fill by terrain type. Use `subdivide=False` — "sections of the same terrain".
  Water(8)/rock(9) are barriers (`zone_label = -1`). `compute_static_features(...)[:,:,20]`
  is the normalized BFS distance-to-boundary (interior depth). `SegmentStep` (the pipeline
  step) uses the related `kit.segmentation._segment_level`, not this function directly;
  `terrain_segment.segment` itself is used by the corpus-extraction/research tooling.

## Rendering (editor-quality)

- `renderers/sprites.py` composites real 32px H3 sprites from the local LOD files. `_decode_frame`
  handles all four H3 DEF formats: 0 (raw), 1 (per-line RLE), 2 (per-line typed RLE),
  **3 (one uint16 offset per 32-px block, row-major)** — getting format 3 wrong mangles every
  mountain/town/monster, so it is the key thing the tests guard.
- `vcmi_mapgen/renderers/sprites_test.py` is the reliability suite: every DEF format decodes to its
  header dimensions and non-empty content, all terrain tiles decode, a corpus-wide sprite
  decode sweep, and renderer determinism. Run `uv run pytest`; tests skip when the H3 LOD
  files are absent.

Load `vcmi-mapgen-pipeline` for how these pieces are wired into steps and a CLI —
this skill is the domain facts each step implements, not the wiring itself. Load
`vcmi_mapgen/steps/AGENTS.md` for the concrete "what a step must do" contract.
