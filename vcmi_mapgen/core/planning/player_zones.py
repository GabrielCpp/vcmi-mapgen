"""The player-zone pick: big land zones that are mutually far apart."""

from collections.abc import Callable, Mapping, Sequence

from vcmi_mapgen.core.model import Zone


def select_player_zones(
    zones_by_level: Mapping[int, Mapping[int, Zone]],
    players: int,
    can_host: Callable[[int, int], bool] = lambda _level, _zid: True,
    preferred: Sequence[tuple[int, int]] = (),
) -> list[tuple[int, int]]:
    """Deterministic player-zone pick across BOTH terrain levels (surface always present;
    underground pooled in only when `--subterrain` is on): big land zones that are MUTUALLY
    FAR APART in (x, y) — the two levels share one coordinate system, so cross-level
    distance is compared the same way as same-level distance. Candidates are land zones
    >= 60 tiles, preferring real zones (>= 100 tiles and >= 1/4 of the largest, pooled across
    levels). The first pick is the largest zone overall; each next pick greedily maximizes
    the minimum centroid distance to the zones already chosen (tie-break: area desc, level,
    zid). A zone ``can_host`` refuses never becomes a candidate. The ``preferred`` land zones
    that can host a town are picked first, in their order, whatever their size, and the
    greedy pick fills the rest. Returns [(level, zid), ...] in player order."""
    cand = [
        (z.area, level, zid, z.centroid)
        for level, zones in zones_by_level.items()
        for zid, z in zones.items()
        if z.terrain_type.is_land and z.area >= 60 and can_host(level, zid)
    ]
    fixed = [
        (z.area, level, zid, z.centroid)
        for level, zid in preferred
        if (z := zones_by_level.get(level, {}).get(zid)) is not None
        and z.terrain_type.is_land
        and can_host(level, zid)
    ][: max(0, players)]
    if fixed and (len(fixed) == players or not cand):
        return [(level, zid) for _a, level, zid, _c in fixed]
    if not cand or players <= 0:
        return []
    cand.sort(key=lambda c: (-c[0], c[1], c[2]))
    amax = cand[0][0]
    pool = [c for c in cand if c[0] >= max(100, amax // 4)]
    if len(pool) < players:  # too few big zones: admit smaller ones
        pool = cand
    chosen = fixed or [pool[0]]
    keys = {(c[1], c[2]) for c in chosen}
    rest = [c for c in pool if (c[1], c[2]) not in keys]
    while len(chosen) < players and rest:
        best = max(
            rest,
            key=lambda c: (
                min((c[3][0] - ch[3][0]) ** 2 + (c[3][1] - ch[3][1]) ** 2 for ch in chosen),
                c[0],
                -c[1],
                -c[2],
            ),
        )
        chosen.append(best)
        rest.remove(best)
    return [(level, zid) for _a, level, zid, _c in chosen]
