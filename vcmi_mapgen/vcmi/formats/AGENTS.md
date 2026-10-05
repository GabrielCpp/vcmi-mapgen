# vcmi/formats/: file codecs

Each module reads or writes one file format. None of them imports from the generator.

## Map

- `defs.py`: the H3 `.def` sprite decoder for all four frame formats.
- `h3m.py`: the `.h3m` parser for RoE, AB, SoD and HotA maps, HotA sub-versions 0 to 9. Each map must end in exactly 124 zero bytes.
- `h3m_scripts.py`: `HotaScripts`, which walks the HotA 9 event-script section so the parser lands on the next section. An unknown script code raises `ScriptError`.
- `h3m_test.py`: synthetic HotA maps for every sub-version, the script walker, and the real HotA map packs of the local install, skipped when absent.
- `json_value.py`: typed narrowing of parsed JSON into objects, lists, ints and strings, and `loads_relaxed`, which parses the JSON with comments and trailing commas that mod files use.
- `lod.py`: the index and reader for the H3 `.lod` sprite archives. Any nonzero compressed size means zlib data, as in VCMI.
- `lod_test.py`: stored and compressed entries of a synthetic `.lod`.
- `vmap/`: the `.vmap` reader, writer and tile-string codecs.
