# VCMI maps — domain & the zone engine

## Formats & identifiers

- `.h3m` (real maps): gzip binary, parsed by `vcmi_mapgen/h3m.py` (`parse_file` → `H3Map`
  with terrain tiles + objects; RoE/AB/SoD only). `.vmap` (editor): zip of relaxed JSON,
  read/written by `vcmi_mapgen/kit/vmap/{reader,writer}.py` (a full `VmapDocument` model —
  header players/teams/victory/defeat, every object, terrain as VCMI tile strings — with an
  `extra` catch-all so an unmodeled key still round-trips losslessly).
- **The corpus** (`maps_vmap/<name>.vmap`, loaded by `kit.objects.load_faithful`) is the
  engine's input. Regenerate from `maps/` with `python -m vcmi_mapgen.extract_vmap`. The
  engine-internal mask charset (`'X'` blocked-entrance vs `'A'` walk-on) is NOT read back
  from a `.vmap`'s `template.mask` (VCMI's own charset can't represent that distinction —
  see `kit.vmap.terrain.vcmi_mask`'s docstring); `load_faithful` re-derives it from
  `ontology.mask_of(animation)` instead, falling back to the file's own mask only when the
  ontology has no data for that animation at all (heroes — their per-portrait animations
  aren't in `objects.txt`'s catalog — where the fallback is safe since a hero's mask has no
  `'B'` cell to begin with).
- Object identity comes from VCMI's own config via `vcmi_mapgen/kit/vcmi_config.py`
  (`resolve(obj_class, obj_subid) → (type, subtype)`). Never guess subtypes. The reference
  C++ format sources are in `vcmi-h3m-format-reference/`.
- A visitable object's template needs `visitableFrom` (the 3×3 approach grid) or the editor
  warns "no visitable directions" — `rebuild.engine.fm_to_document` sets it.
- Footprints: `kit.objects.mask_cells(mask, x, y)` expands a mask anchored at its
  bottom-right cell; `'B'` = blocking, `'A'`/`'V'` = visitable/overlay, `' '` = empty.

## Segmentation

- `terrain_segment.segment(level, subdivide=False)` → `(zones, zone_label)`: 4-conn
  flood-fill by terrain type. Use `subdivide=False` — "sections of the same terrain".
  Water(8)/rock(9) are barriers (`zone_label = -1`). `compute_static_features(...)[:,:,20]`
  is the normalized BFS distance-to-boundary (interior depth).

## The zone template + identity guarantee

- `rebuild.engine.extract_template(name)` (wrapped by `steps.extract_template.ExtractTemplateStep`)
  records, per zone, `bbox / centroid / mask_rel(sorted) / shape_hash / label` and per
  object `{purpose, identity, anchor_off, canon(depth,sweep)}`. Barrier-anchored objects go
  to a per-level absolute bucket.
- `rebuild_map(template, target_terrain, identity=True)` (wrapped by
  `steps.rebuild_map.RebuildMapStep`) matches each template zone to the target zone with
  the same `(mask_rel, bbox)` and replays objects at `bbox_min + anchor_off`
  — **pure integer ⇒ bit-exact when the shape is unchanged.** `rebuild --identity --verify`
  multiset-compares all levels (via `steps.verify.VerifyStep`) and prints `IDENTITY OK: N/N`.
  Identity is **never re-rolled** (no `pick_variant`) so relational portals survive.
- `zone_features(zone, objs, canon_zone)` indexes each object's canonical (depth, sweep)
  via `_obj_canon` — a boundary object (e.g. a rim mountain) can be anchored OFF the zone
  entirely (gathered in by footprint overlap, see `_bucket_objects`), so canon must be read
  from the rim-most footprint tile that IS in the zone, not the raw anchor tile. Don't
  index `canon_zone[(o["x"], o["y"])]` directly for an object that may be a boundary object.

## Stretch (different shape)

- **Stretch = the same objects at the same relative placement on a LARGER tile grid.** VCMI
  objects are fixed-size tile objects, so positions scale by the bbox-affine and footprints
  do NOT. Rigid gameplay = one tile, no overlap (snap to a free zone tile); decoration keeps
  its relative spot, may overlap decoration but must NOT bury gameplay or sit on a barrier; a
  VCMI-invalid (untraversable) result is rejected. Zone objects are gathered by **footprint
  overlap** (so the edge rim of mountains and edge mines come with the zone). `rebuild
  "<name>" --zone N --deform` (wrapped by `steps.deform_warp.DeformWarpStep`) warps that one
  zone's pattern onto a deformed target shape — `deform_terrain_level(src_terr, zone, W, H,
  ...)` takes the FULL source terrain grid as `src_terr`, not the zone dict; passing the
  zone dict where the grid belongs is a `TypeError` that's easy to reintroduce.
- Do NOT redo the rejected attempts: image-warp/pixel-resize (violates fixed-size),
  wall-fill (adds foreign objects), coverage-stretch (does not look the same).

## Rendering (editor-quality)

- `renderers/sprites.py` composites real 32px H3 sprites from the local LOD files. `_decode_frame`
  handles all four H3 DEF formats: 0 (raw), 1 (per-line RLE), 2 (per-line typed RLE),
  **3 (one uint16 offset per 32-px block, row-major)** — getting format 3 wrong mangles every
  mountain/town/monster, so it is the key thing the tests guard.
- `vcmi_mapgen/renderers/sprites_test.py` is the reliability suite: every DEF format decodes to its
  header dimensions and non-empty content, all terrain tiles decode, a corpus-wide sprite
  decode sweep, renderer determinism, and a golden **rebuilt == source** pixel-identical check.
  Run `uv run pytest`; tests skip when the H3 LOD files are absent.

Load `vcmi-mapgen-pipeline` for how these pieces are wired into steps and a CLI —
this skill is the domain facts each step implements, not the wiring itself.
