"""The .vmap container format: a full, round-trip-safe reader/writer plus the
stateless template-mask codecs the rest of the engine needs."""

from vcmi_mapgen.vcmi.formats.vmap.document import PlayerSlot, VmapDocument, VmapObject
from vcmi_mapgen.vcmi.formats.vmap.mask import build_mask_from_h3m
from vcmi_mapgen.vcmi.formats.vmap.reader import header_fields, read, read_header
from vcmi_mapgen.vcmi.formats.vmap.terrain import (
    export_mask,
    vcmi_mask,
    visitable_from,
)
from vcmi_mapgen.vcmi.formats.vmap.writer import write

__all__ = [
    "PlayerSlot",
    "VmapDocument",
    "VmapObject",
    "build_mask_from_h3m",
    "export_mask",
    "header_fields",
    "read",
    "read_header",
    "vcmi_mask",
    "visitable_from",
    "write",
]
