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
  `.vmap`. It re-derives the mask from `ontology.mask_of(animation)` instead.
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

## Segmentation

- `kit.terrain_segment.segment(terrain_level)` returns `(zones, zone_label)`. It is a
  4-connected flood fill by terrain type. Water (8) and rock (9) are barriers, with
  `zone_label` set to -1.
- `kit.terrain_segment.compute_static_features(...)` returns a per-tile feature array.
  Channel 20 is the BFS distance to the zone boundary, normalised by the square root of
  the zone area. It measures interior depth.
- `kit.segmentation.segment_level(level)` runs both and adds per-zone canonical
  coordinates. `SegmentStep` calls it.

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
