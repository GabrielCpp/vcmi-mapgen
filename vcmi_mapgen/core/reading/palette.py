"""Palette readings of a place map (map-math 1.4): how many of its place borders join two
places of one dominant terrain, and how many same-dominant regions its places form. The
miner reads the corpus with them and the terrain log reads a generated level with the same
functionals."""

from collections.abc import Collection, Iterable, Mapping

from vcmi_mapgen.core.reading.borders import Pair


def same_share(dominant: Mapping[int, int], pairs: Collection[Pair]) -> float | None:
    """The share of adjacent place pairs whose two places share a dominant, None without a
    pair."""
    if not pairs:
        return None
    return sum(dominant[p] == dominant[q] for p, q in pairs) / len(pairs)


def palette_regions(dominant: Mapping[int, int], pairs: Iterable[Pair]) -> int:
    """The number of connected components of the graph on ``dominant``'s places whose
    edges are the adjacent pairs of one dominant."""
    root = {p: p for p in dominant}

    def find(p: int) -> int:
        while root[p] != p:
            root[p] = root[root[p]]
            p = root[p]
        return p

    for p, q in pairs:
        if dominant[p] == dominant[q]:
            root[find(p)] = find(q)
    return len({find(p) for p in dominant})


def same_by_roles(
    roles: Mapping[int, str], dominant: Mapping[int, int], pairs: Iterable[Pair]
) -> dict[str, tuple[int, int]]:
    """``"roleA|roleB"`` with roleA <= roleB -> (same-dominant pairs, all pairs)."""
    out: dict[str, tuple[int, int]] = {}
    for p, q in pairs:
        key = "|".join(sorted((roles[p], roles[q])))
        same, total = out.get(key, (0, 0))
        out[key] = (same + (dominant[p] == dominant[q]), total + 1)
    return dict(sorted(out.items()))
