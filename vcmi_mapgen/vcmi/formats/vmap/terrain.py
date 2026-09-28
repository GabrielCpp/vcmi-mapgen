"""VCMI template-mask encoding and decoding, the stateless format primitives `.vmap`
object footprints are built from. Tile strings live in `vcmi.tiles`."""

from collections.abc import Sequence

from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.footprint import mask_rows


def visitable_from(mask: Sequence[str]) -> list[str] | None:
    """The 3x3 approach grid VCMI needs for visitable templates. Buildings (have
    blocked body) are entered from the sides/below; free-standing pickups/monsters
    from all 8 directions. None for pure decoration (no visitable tile)."""
    if not any(ch in "AX" for r in mask for ch in r):  # 'A' or 'X' = a visitable tile
        return None
    if any(ch in "BX" for r in mask for ch in r):  # has a blocked body -> a building
        return ["---", "+-+", "+++"]
    return ["+++", "+-+", "+++"]


def vcmi_mask(mask: Sequence[str]) -> list[str]:
    """Translate an engine-internal mask to VCMI's template charset for .vmap export.

    Our masks use 'X' for a blocked ENTRANCE cell (entered from below). VCMI's
    ObjectTemplate parser only knows ' 0VBHAT' and logs "Unrecognized char X in template
    mask", dropping the cell to FREE — which made every mine/town silently unvisitable
    in-game (no VISITABLE cell survived). VCMI's 'A' = VISIBLE|BLOCKED|VISITABLE is the
    exact semantic of our 'X' (and of our walk-on 'A' — monsters/pickups are
    blocked-visitable in H3), so both map onto it.

    NOTE this is LOSSY: a VCMI-charset mask can never be translated back into 'X' vs 'A'
    -- see `vcmi.formats.vmap.reader`'s docstring and `vcmi/load.py`'s docstring for why the
    engine-internal mask must always be re-derived from the ontology, never read back
    out of a .vmap's `template.mask`.
    """
    return [row.replace("X", "A") for row in mask]


def _trim_v(mask: Sequence[str]) -> list[str]:
    """The mask minus its all-'V' border rows/columns — the footprint core two masks must
    share to be the same object shape."""
    rows = [i for i, r in enumerate(mask) if set(r) - {"V"}]
    cols = [c for c in range(len(mask[0])) if any(row[c] != "V" for row in mask)]
    if not rows or not cols:
        return ["V"]
    return [mask[i][min(cols) : max(cols) + 1] for i in range(min(rows), max(rows) + 1)]


def export_mask(o: PlacedObject) -> list[str]:
    """The template mask written to the .vmap: the ontology's sprite-extent mask
    (`vmap_mask_of` — VCMI draws an object only on mask-covered tiles, so the bbox-trimmed
    internal mask truncates tall sprites in-game) when its footprint core agrees with the
    instance mask; otherwise the instance mask translated to VCMI's charset (the editor
    table and a map instance legitimately disagree for a handful of corpus dwellings)."""
    inst = vcmi_mask(mask_rows(o.footprint))
    vm = ON.vmap_mask_of(o.kind)
    return list(vm) if vm and _trim_v(vm) == _trim_v(inst) else inst
