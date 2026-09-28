# vcmi/formats/vmap/: the `.vmap` container

A full, round-trip-safe reader and writer, plus the stateless tile-string and mask codecs.

## Map

- `document.py`: the `VmapDocument` model, with an `extra` catch-all for unmodelled keys.
- `mask.py`: decodes an h3m template's block and visit bitmasks into the B/A/V/X charset.
- `reader.py`: unzips a `.vmap` and parses it into a `VmapDocument`.
- `terrain.py`: template-mask encoding and decoding.
- `writer.py`: serialises a `VmapDocument` back into a `.vmap` zip.
