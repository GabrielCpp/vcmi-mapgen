"""The .vmap container format: a full, round-trip-safe reader/writer plus the
stateless tile-string / template-mask codecs the rest of the engine needs."""

from vcmi_mapgen.kit.vmap.document import PlayerSlot, VmapDocument, VmapObject
from vcmi_mapgen.kit.vmap.mask import build_mask_from_h3m
from vcmi_mapgen.kit.vmap.reader import header_fields, read, read_header
from vcmi_mapgen.kit.vmap.terrain import (
    RIVER,
    ROAD,
    TCODE,
    decode_tile_string,
    export_mask,
    tile_string,
    vcmi_mask,
    visitable_from,
)
from vcmi_mapgen.kit.vmap.writer import write

__all__ = [
    "RIVER",
    "ROAD",
    "TCODE",
    "PlayerSlot",
    "VmapDocument",
    "VmapObject",
    "build_mask_from_h3m",
    "decode_tile_string",
    "export_mask",
    "header_fields",
    "read",
    "read_header",
    "tile_string",
    "vcmi_mask",
    "visitable_from",
    "write",
]
