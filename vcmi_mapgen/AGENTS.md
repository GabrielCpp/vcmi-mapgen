# VCMI maps: the domain

## Formats and identifiers

- `.h3m` is a real map, a gzip binary. `h3m.parse_file` parses it into an `H3Map` with
  terrain tiles and objects. It handles RoE, AB and SoD only.
- `.vmap` is the editor format, a zip of relaxed JSON. `vcmi/formats/vmap/reader.py` and
  `vcmi/formats/vmap/writer.py` read and write it through a full `VmapDocument` model. The model
  covers header players, teams, victory, defeat, every object, and terrain as VCMI tile
  strings. Its `extra` catch-all lets an unmodelled key round-trip losslessly.
- **The corpus** is `data/corpus/vmap/<name>.vmap`, loaded by `corpus.maps.load_corpus_map`
  as a `MapState`, the same type a generated map is.
  `python -m vcmi_mapgen.cli extract-vmap` regenerates it from `data/corpus/h3m/`.
- The internal mask charset tells `'X'` (blocked entrance) apart from `'A'` (walk-on).
  VCMI's own charset cannot, so `vcmi.load.load_map` never reads that distinction back from a
  `.vmap`. It re-derives the mask from `vcmi.catalog.objects.mask_of(animation)` instead.
  `vcmi.formats.vmap.terrain.vcmi_mask` has the details. The file's own mask is the fallback only
  when the ontology has no data for that animation, which is the case for heroes.
- Object identity comes from VCMI's own config: `vcmi.config.VcmiConfig.resolve(obj_class,
  obj_subid)` returns `(type, subtype)`. Never guess a subtype. The C++ format sources
  are in `vcmi-h3m-format-reference/`.
- A visitable object's template needs `visitableFrom`, the 3x3 approach grid, or the
  editor warns "no visitable directions". `vcmi.formats.vmap.terrain.visitable_from` derives it
  from the mask, and `vcmi/export.py` sets it on every exported object.
- Footprints: the core never sees a mask string. `core.model.Footprint` holds an object's
  cells as offsets from its bottom-right anchor, each with a `Role`: blocking, entrance,
  visit or overlay. `vcmi.footprint.footprint_of(rows)` decodes the `'B'`, `'X'`, `'A'`
  and `'V'` charset into one, and `mask_rows(fp)` encodes it back for export. Only
  `vcmi/` holds that charset. `core.placement.footprint.anchored_cells(fp, x, y)` expands a footprint
  at a position, and `core.model.footprint(obj)` gives each covered tile with its `Role`.

## Terrain

- `core.model.terrain.Terrain` is the terrain vocabulary the steps use. Compare against its
  members and its `is_water`, `is_barrier` and `is_land` properties, never against a bare
  code such as 8.
- `vcmi.terrain.TERRAINS` maps each `Terrain` to its Heroes III code, VCMI tile prefix and
  name. `name_of(code)` gives the name the catalog keys on. No other module holds a copy of
  those codes, prefixes or names.

## Purposes and resources

- `core.model.purpose.Purpose` names what an object is placed for. Steps compare against
  its members and filter by its groups `VISIT_PURPOSES` and `COUNTED`, never against a bare
  string such as `"GUARD"`.
- `vcmi.catalog.objects.purpose_of_type(type)` answers the purpose of a VCMI object type
  through its class id in `data/catalog/vcmi_types.json`. `regen-ontology` rewrites that
  table from VCMI's config.
- `core.model.resource.Resource` names the eight resources.

## Segmentation

- `core.grid.segment.segment_level(level)` returns `(zones, zone_label, canonical)`.
  `TerrainStep` calls it through `terrain_gen/levels.py` and provides
  `Segmentation(zones, zone_label)` from `terrain_gen/result.py`.
- `zone_label` is a `ZoneLabel` grid read `[y][x]`. The entrance and gate geometry in
  `core/planning/entrances.py` reads it. `label_zones(zones)` rebuilds one from
  hand-built zones in tests.
- The segmentation is a 4-connected flood fill by terrain type. Water and rock are
  barriers (`Terrain.is_barrier`), with `zone_label` set to -1.
- Each zone tile's canonical coordinates are `(depth, sweep)`. Depth comes from the BFS
  distance to the zone boundary, renormalised to the zone's own range. Sweep is the
  tile's angle around the zone centroid.

## Rendering

- `vcmi/formats/defs.py` decodes H3 DEF sprites. `_decode_frame` handles all four
  formats: 0 (raw), 1 (per-line RLE), 2 (per-line typed RLE) and 3 (one uint16 offset
  per 32px block, row-major). A format 3 mistake mangles every mountain, town and
  monster, so format 3 is the main thing `vcmi/formats/defs_test.py` guards. It checks
  that every DEF format decodes to its header size with content, and that known object
  sprites decode.
- `renderers/sprites.py` composites real 32px H3 sprites from the local LOD files.
  `renderers/sprites_test.py` checks that every terrain tile decodes, the decode
  coverage across corpus sprites, and that rendering is deterministic.
- All of these tests skip when the H3 LOD files are absent.

## History that is not the current design

Until 2026-09-06 the repo held a zone-replay engine. It recorded each corpus zone's
object pattern and replayed it onto a target shape, and it came with `rebuild`,
`extract` and a bit-exact identity check. Commit `4e80daf` deleted it.
`docs/architecture.md` still describes that engine. Read it as history, not as a
description of the generator.

Load `vcmi-mapgen-pipeline` for how the steps are wired together.
