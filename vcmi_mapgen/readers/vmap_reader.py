"""VmapReader — load a .vmap file into a MapState for rendering."""

from __future__ import annotations

from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.vmap.terrain import decode_tile_string


class VmapReader:
    """Load a VCMI .vmap file into a MapState with surfs, cells, objs, and size.

    The resulting MapState can be passed directly to PngRenderer (with overlays)
    or VmapRenderer for a round-trip re-export.  Fields not stored in a .vmap
    (zones, gate_*, player_towns, ledger, …) are left at their dataclass defaults.

    Usage::

        state = VmapReader().read("out/vmap/mymap.vmap")
        img = PngRenderer(index).render(state, level=0)
    """

    def read(self, path: str) -> MapState:
        doc = VM.read(path)
        state = MapState(size=max(doc.width, doc.height))
        for level, grid in enumerate(doc.terrain):
            state.surfs[level] = grid
            state.cells[level] = [[decode_tile_string(t) for t in row] for row in grid]
        state.objs = [
            PlacedObject(
                x=o.x,
                y=o.y,
                level=o.level,
                purpose=ON.purpose_of_type(o.type) or Purpose.UNKNOWN,
                type=o.type,
                subtype=o.subtype,
                animation=o.animation,
                mask=ON.mask_of(o.animation) if ON.has_animation(o.animation) else tuple(o.mask),
            )
            for o in doc.objects
        ]
        return state
