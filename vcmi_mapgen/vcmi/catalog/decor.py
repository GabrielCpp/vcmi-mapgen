"""Decoration pools and categories, and object-class pools built over them.

`EXCLUDE_DECOR_TYPES` names the water-feature categories no terrain ever takes. The catalog
marks them blocking, but they read as misplaced water rather than as an obstacle, so the
pools, the category learning and the decode all skip them.
"""

from collections.abc import Iterable
from random import Random

from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.vcmi.catalog.objects import (
    footprint_size,
    gameplay_pool,
    identity_of,
    indexes,
    is_blocking,
    terrain_keys,
    terrain_name,
)
from vcmi_mapgen.vcmi.terrain import TERRAINS

EXCLUDE_DECOR_TYPES: set[str] = {"LAKE", "FROZEN_LAKE", "RIVER_DELTA", "KELP", "REEF", "LAKE_2"}


def decor_pool(
    terrain: str | int,
    *,
    blocking: bool | None = None,
    max_cells: int | None = None,
    exclude_types: Iterable[str] = (),
) -> list[Identity]:
    """DECORATION placement identities native to a terrain (name or id), filtered by optional
    predicates: ``blocking`` (footprint blocks or not), ``max_cells`` (bounding-box area cap),
    ``exclude_types`` (ontology type-level names to drop, e.g. water features)."""
    idx = indexes()
    name = terrain_name(terrain)
    exclude = set(exclude_types)
    out: list[Identity] = []
    seen: set[str] = set()
    for k in terrain_keys(name):
        for anim in idx.decor_by_terrain.get(k, ()):
            if anim in seen or idx.anim_category.get(anim) in exclude:
                continue
            if blocking is not None and is_blocking(anim) != blocking:
                continue
            if max_cells is not None and footprint_size(anim) > max_cells:
                continue
            seen.add(anim)
            out.append(identity_of(anim))
    return out


def veg_categories() -> list[str]:
    """The decoration category vocabulary = the ontology DECORATION type-level keys."""
    return list(indexes().veg_categories)


def category_of(animation: str) -> int | None:
    """Index of an animation's decoration category in :func:`veg_categories` (None if not decor;
    case-insensitive)."""
    idx = indexes()
    typ = idx.anim_category.get((animation or "").lower())
    return idx.veg_categories.index(typ) if typ in idx.veg_categories else None


def pool(
    object_class: str,
    terrain: str | int,
    *,
    blocking: bool | None = None,
    max_cells: int | None = None,
    exclude_types: Iterable[str] = (),
) -> list[Identity]:
    """Every identity of an object class that may stand on a terrain. ``object_class`` is a
    gameplay purpose (MINE, DWELLING, ...) or a decoration category (CRATER, mountain, ...).
    Terrain-specific tags beat the generic 'land' tag. Empty when the class has nothing native
    to that terrain."""
    idx = indexes()
    if object_class in idx.veg_categories:
        return [
            i
            for i in decor_pool(
                terrain, blocking=blocking, max_cells=max_cells, exclude_types=exclude_types
            )
            if idx.anim_category.get(i.animation) == object_class
        ]
    return [
        i
        for i in gameplay_pool(terrain, object_class)
        if (blocking is None or is_blocking(i.animation) == blocking)
        and (max_cells is None or footprint_size(i.animation) <= max_cells)
        and idx.anim_category.get(i.animation) not in set(exclude_types)
    ]


def pick(object_class: str, terrain: str | int, rng: Random) -> Identity | None:
    """One identity of an object class allowed on a terrain, drawn uniformly with ``rng``.
    None when the class has nothing native to that terrain."""
    candidates = sorted(pool(object_class, terrain), key=lambda i: i.animation)
    return rng.choice(candidates) if candidates else None


def decode_identity(
    category: int | str | None, terrain: str | int, rng: Random | None = None
) -> Identity | None:
    """Pick a concrete DECORATION identity of a category (index or type name) native to a terrain
    (falls back to the terrain-independent 'land' bucket). Uniform; deterministic if rng is None."""
    idx = indexes()
    if isinstance(category, str):
        typ = category
    elif category is not None and 0 <= category < len(idx.veg_categories):
        typ = idx.veg_categories[category]
    else:
        return None
    candidates = pool(typ, terrain)
    if not candidates:
        return None
    if rng is None:
        return candidates[0]
    return pick(typ, terrain, rng)


def category_terrain_matrix() -> list[list[bool]]:
    """bool[len(TERRAINS)][len(categories)]: a category is present on a terrain (incl. the
    terrain-independent 'land'/'water' bucket) in the taxonomy."""
    idx = indexes()
    cidx = {t: i for i, t in enumerate(idx.veg_categories)}
    M = [[False] * len(idx.veg_categories) for _ in range(len(TERRAINS))]
    for tid, name in ((t.value, c.name) for t, c in TERRAINS.items()):
        for k in terrain_keys(name):
            for anim in idx.decor_by_terrain.get(k, ()):
                cat = idx.anim_category.get(anim)
                c = cidx.get(cat) if cat is not None else None
                if c is not None:
                    M[tid][c] = True
    return M
