"""Object clustering/anchor helpers used by research/zone_skeleton.py.

Not needed by the map-generation or identity-rebuild pipelines themselves — kept here
because they're dev-only tooling for exploring gameplay-object set-piece structure.
"""
import collections

# A placement GROUP forms around a single anchor that must be a VISITABLE destination (interacted
# with by standing on its 'A' visit tile) or a PICKABLE reward — never a guard, lone INFO sign, or
# decoration (the user's rule: "cluster around visitable object and pickable resources / artifacts").
# Anything else (INFO, decoration) may only join a group as a member.
ANCHOR_PURPOSES = {
    "TOWN", "MINE", "DWELLING", "BANK",                    # visitable destinations
    "STAT_PERMANENT", "SPELL_SKILL", "BONUS_TEMP", "MANA",  # visitable bonus/skill sites
    "REWARD_PICKUP", "RESOURCE_PILE",                      # pickable loot / resource piles
}
# Anchor priority when a cluster holds several eligible objects (tie broken by larger footprint):
# the most "important" destination organizes the set-piece (a town over a mine over a pickup).
_ANCHOR_PRIO = {"TOWN": 9, "BANK": 8, "MINE": 7, "DWELLING": 6, "STAT_PERMANENT": 5,
                "SPELL_SKILL": 4, "BONUS_TEMP": 3, "MANA": 2, "REWARD_PICKUP": 1, "RESOURCE_PILE": 0}
GROUP_EPS = 3            # single-linkage radius (tiles) that ties two gameplay objects into one group:
#                          3 balances corpus multi-object fraction (~0.59, vs map-level 0.64) against
#                          tight set-piece diameter (~2 tiles) — 4 chains whole dense zones together.


def _manh(a, b):
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def _footprint_area(o):
    """Bounding-box cell count of an object's mask (proxy for object size)."""
    m = o.get("mask") or []
    return len(m) * (len(m[0]) if m else 0)


def _cluster_objects(objs, eps=GROUP_EPS):
    """Single-linkage spatial clusters: two objects are linked when their Manhattan distance is
    <= eps; clusters are the connected components. O(n^2) over a zone's handful of gameplay objects."""
    n = len(objs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _manh(objs[i], objs[j]) <= eps:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    comps = collections.defaultdict(list)
    for i, o in enumerate(objs):
        comps[find(i)].append(o)
    return list(comps.values())


def _group_anchor(cluster):
    """The object that organizes a cluster: the highest-priority ANCHOR_PURPOSES member (visitable
    or pickable), ties broken by larger footprint. None if the cluster has no eligible anchor."""
    cands = [o for o in cluster if o.get("_purpose") in ANCHOR_PURPOSES]
    if not cands:
        return None
    return max(cands, key=lambda o: (_ANCHOR_PRIO.get(o["_purpose"], -1), _footprint_area(o)))


def _mask_anchor_cells(mask, x, y):
    """Yield the (tx, ty) of the mask's 'A' (visitable-anchor) cells — the tile the hero stands
    on / that triggers the object — using the same bottom-right anchoring as ``OR.mask_cells``
    (col 0 is the leftmost tile, `tx = x - (ww-1-c)`; see OR.mask_cells's docstring)."""
    hh = len(mask)
    for r, row in enumerate(mask):
        ww = len(row)
        for c, ch in enumerate(row):
            if ch == "A":
                yield x - (ww - 1 - c), y - (hh - 1 - r)
