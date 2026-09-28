# vcmi/formats/: file codecs

Each module reads or writes one file format. None of them imports from the generator.

## Map

- `defs.py`: the H3 `.def` sprite decoder for all four frame formats.
- `h3m.py`: the `.h3m` parser for RoE, AB and SoD maps.
- `json_value.py`: typed narrowing of parsed JSON into objects, lists, ints and strings.
- `lod.py`: the index and reader for the H3 `.lod` sprite archives.
- `vmap/`: the `.vmap` reader, writer and tile-string codecs.
