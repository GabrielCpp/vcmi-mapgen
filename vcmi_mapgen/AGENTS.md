# VCMI maps: the domain

## Formats and identifiers

- `.h3m` is a real map, a gzip binary. `h3m.parse_file` parses it into an `H3Map` with
  terrain tiles and objects. It handles RoE, AB and SoD only.
- `.vmap` is the editor format, a zip of relaxed JSON. `kit/vmap/reader.py` and
  `kit/vmap/writer.py` read and write it through a full `VmapDocument` model. The model
  covers header players, teams, victory, defeat, every object, and terrain as VCMI tile
  strings. Its `extra` catch-all lets an unmodelled key round-trip losslessly.
- **The corpus** is `maps_vmap/<name>.vmap`, loaded by `kit.objects.load_faithful`.
  `python -m vcmi_mapgen.extract_vmap` regenerates it from `maps/`.
- The internal mask charset tells `'X'` (blocked entrance) apart from `'A'` (walk-on).
  VCMI's own charset cannot, so `load_faithful` never reads that distinction back from a
  `.vmap`. It re-derives the mask from `vcmi.catalog.objects.mask_of(animation)` instead.
  `kit.vmap.terrain.vcmi_mask` has the details. The file's own mask is the fallback only
  when the ontology has no data for that animation, which is the case for heroes.
- Object identity comes from VCMI's own config: `kit.vcmi_config.resolve(obj_class,
  obj_subid)` returns `(type, subtype)`. Never guess a subtype. The C++ format sources
  are in `vcmi-h3m-format-reference/`.
- A visitable object's template needs `visitableFrom`, the 3x3 approach grid, or the
  editor warns "no visitable directions". `kit.vmap.terrain.visitable_from` derives it
  from the mask, and `renderers/vmap.py` sets it on every exported object.
- Footprints: `kit.objects.mask_cells(mask, x, y)` expands a mask anchored at its
  bottom-right cell. `'B'` is blocking, `'A'` and `'V'` are visitable or overlay, and
  `' '` is empty. `models.footprint(obj)` gives each covered tile with its `Role`.

## Terrain

- `core.model.terrain.Terrain` is the terrain vocabulary the steps use. Compare against its
  members and its `is_water`, `is_barrier` and `is_land` properties, never against a bare
  code such as 8.
- `vcmi.terrain.TERRAINS` maps each `Terrain` to its Heroes III code, VCMI tile prefix and
  name. `name_of(code)` gives the name the catalog keys on. No other module holds a copy of
  those codes, prefixes or names.

## Segmentation

- `core.grid.segment.segment_level(level)` returns `(zones, zone_label, canonical)`. It
  is the module's one public entry, and `SegmentStep` calls it.
- The segmentation is a 4-connected flood fill by terrain type. Water and rock are
  barriers (`Terrain.is_barrier`), with `zone_label` set to -1.
- Each zone tile's canonical coordinates are `(depth, sweep)`. Depth comes from the BFS
  distance to the zone boundary, renormalised to the zone's own range. Sweep is the
  tile's angle around the zone centroid.

## Rendering

- `renderers/sprites.py` composites real 32px H3 sprites from the local LOD files.
  `_decode_frame` handles all four H3 DEF formats: 0 (raw), 1 (per-line RLE), 2
  (per-line typed RLE) and 3 (one uint16 offset per 32px block, row-major). A format 3
  mistake mangles every mountain, town and monster, so format 3 is the main thing the
  tests guard.
- `renderers/sprites_test.py` checks that the LOD index loads, that every DEF format
  decodes to its header size with content, that every terrain tile and known object
  sprite decodes, the decode coverage across corpus sprites, and that rendering is
  deterministic. These tests skip when the H3 LOD files are absent.

## History that is not the current design

Until 2026-09-06 the repo held a zone-replay engine. It recorded each corpus zone's
object pattern and replayed it onto a target shape, and it came with `rebuild`,
`extract` and a bit-exact identity check. Commit `4e80daf` deleted it.
`docs/architecture.md` still describes that engine. Read it as history, not as a
description of the generator.

Load `vcmi-mapgen-pipeline` for how the steps are wired together.
