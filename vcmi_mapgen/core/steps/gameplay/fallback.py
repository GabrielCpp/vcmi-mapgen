"""The smaller objects a placement falls back to when its first pick finds no spot."""

from __future__ import annotations

from collections.abc import Sequence

from vcmi_mapgen.core.model import Footprint, Identity, Role
from vcmi_mapgen.core.placement.footprint import footprint_cells
from vcmi_mapgen.core.placement.site import ZoneSite

_TIE_ORDER = (None, Role.VISIT, Role.BLOCKING, Role.OVERLAY, Role.ENTRANCE)


def _footprint_size(ident: Identity) -> int:
    return len(footprint_cells(ident.footprint, 0, 0)[0])


def _shape_key(fp: Footprint) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(_TIE_ORDER.index(role) for role in row) for row in fp.grid())


def smaller(site: ZoneSite, pool: Sequence[Identity], ident: Identity) -> list[Identity]:
    """One object of ``pool`` per footprint shape smaller than ``ident``'s, the largest shape
    first, each drawn from the site's stream."""
    size = _footprint_size(ident)
    by_shape: dict[Footprint, list[Identity]] = {}
    for cand in sorted(pool, key=lambda i: i.kind):
        if _footprint_size(cand) < size:
            by_shape.setdefault(cand.footprint, []).append(cand)
    shapes = sorted(
        by_shape.values(), key=lambda ids: (-_footprint_size(ids[0]), _shape_key(ids[0].footprint))
    )
    return [site.rng.choice(ids) for ids in shapes]
