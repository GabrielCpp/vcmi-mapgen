"""Zone-shape planning: entrance, gate and front geometry.
Shared by the gameplay, gated and vegetation steps' entrance and backbone logic."""

import collections
from collections.abc import Collection, Iterable, Mapping

from vcmi_mapgen.core.grid.geometry import NB4
from vcmi_mapgen.core.model import Entrance, Tile, Zone

ENTRANCE_W = 3  # entrance band width in front tiles per side (hero + guard fit through)
LONG_FRONT = 20  # a zone-pair front at least this long earns a second entrance
MAX_ENTRANCES = 2  # "a few" — hard cap on planned crossings per zone pair
MIN_ENTRANCE_SEP = 12  # Chebyshev floor between two entrances of the same pair


def zone_fronts(ts: Iterable[Tile], zones: Mapping[int, Zone], zid: int) -> dict[int, list[Tile]]:
    """Full contact FRONTS: {neighbour zid: [zone tiles 4-touching that neighbour]}. The complete
    per-pair border segment — `zone_gates` collapses each front to one tile; `zone_gate_bands`
    keeps a corpus-wide band of it."""
    owner: dict[Tile, int] = {}
    for zz, z in zones.items():
        for t in z.tiles_set:
            owner[t] = zz
    contacts: collections.defaultdict[int, list[Tile]] = collections.defaultdict(list)
    for x, y in ts:
        for dx, dy in NB4:
            o = owner.get((x + dx, y + dy))
            if o is not None and o != zid:
                contacts[o].append((x, y))
    return contacts


def zone_gate_bands(
    ts: Collection[Tile],
    zones: Mapping[int, Zone],
    zid: int,
    open_frac: float = 0.5,
    min_w: int = 3,
) -> list[tuple[Tile, frozenset[Tile]]]:
    """Wide gates — corpus zone 'gates' are broad terrain borders, not 1-tile corridors.

    Returns [(rep, band)] per neighbouring zone: `rep` is the single representative tile
    (identical to `zone_gates`) and `band` is a frozenset of contact-front tiles around it —
    the corpus-like OPEN share of the front (`open_frac` = fraction of corpus zone-border
    tiles left passable, mined per terrain), never fewer than `min_w` tiles. The protected
    web keeps the whole band vegetation-free, so the border stays as open as real maps.
    Isolated pockets get the synthesized antipodal pair with a small border band each."""
    contacts = zone_fronts(ts, zones, zid)
    out: list[tuple[Tile, frozenset[Tile]]] = []
    for o in sorted(contacts):
        tiles = contacts[o]
        mx = sum(t[0] for t in tiles) / len(tiles)
        my = sum(t[1] for t in tiles) / len(tiles)
        rep = min(set(tiles), key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2)
        k = min(len(set(tiles)), max(min_w, round(open_frac * len(set(tiles)))))
        band = sorted(set(tiles), key=lambda t: (max(abs(t[0] - rep[0]), abs(t[1] - rep[1])), t))[
            :k
        ]
        out.append((rep, frozenset(band)))
    if len(out) < 2:
        border = [t for t in ts if any((t[0] + dx, t[1] + dy) not in ts for dx, dy in NB4)]
        if border:
            mx = sum(x for x, _ in ts) / len(ts)
            my = sum(y for _, y in ts) / len(ts)
            a = max(border, key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2)
            b = max(border, key=lambda t: (t[0] - a[0]) ** 2 + (t[1] - a[1]) ** 2)
            reps = {r for r, _band in out}
            for g in (a, b):
                if g not in reps:
                    band = frozenset(
                        t for t in border if max(abs(t[0] - g[0]), abs(t[1] - g[1])) <= min_w // 2
                    )
                    out.append((g, band | {g}))
    return out


def _pair_fronts(zones: Mapping[int, Zone]) -> collections.defaultdict[tuple[int, int], set[Tile]]:
    owner: dict[Tile, int] = {}
    for zz, z in zones.items():
        for t in z.tiles_set:
            owner[t] = zz
    fronts: collections.defaultdict[tuple[int, int], set[Tile]] = collections.defaultdict(
        set
    )  # ordered pair (a, b) -> a-side tiles
    for t, zz in owner.items():
        for dx, dy in NB4:
            o = owner.get((t[0] + dx, t[1] + dy))
            if o is not None and o != zz:
                fronts[(zz, o)].add(t)
    return fronts


def _pair_reps(
    Ta: list[Tile], Tb: list[Tile], long_front: int, max_entrances: int, min_sep: int
) -> list[tuple[Tile, Tile]]:
    mx = sum(t[0] for t in Ta) / len(Ta)
    my = sum(t[1] for t in Ta) / len(Ta)
    rep_a = min(Ta, key=lambda t: ((t[0] - mx) ** 2 + (t[1] - my) ** 2, t))
    rep_b = min(Tb, key=lambda t: ((t[0] - rep_a[0]) ** 2 + (t[1] - rep_a[1]) ** 2, t))
    reps = [(rep_a, rep_b)]
    if len(Ta) >= long_front and max_entrances >= 2:
        rep_a2 = max(Ta, key=lambda t: (max(abs(t[0] - rep_a[0]), abs(t[1] - rep_a[1])), t))
        if max(abs(rep_a2[0] - rep_a[0]), abs(rep_a2[1] - rep_a[1])) >= min_sep:
            rep_b2 = min(Tb, key=lambda t: ((t[0] - rep_a2[0]) ** 2 + (t[1] - rep_a2[1]) ** 2, t))
            reps.append((rep_a2, rep_b2))
    return reps


def plan_entrances(
    zones: Mapping[int, Zone],
    entrance_w: int = ENTRANCE_W,
    long_front: int = LONG_FRONT,
    max_entrances: int = MAX_ENTRANCES,
    min_sep: int = MIN_ENTRANCE_SEP,
) -> dict[int, list[Entrance]]:
    """Map-level entrance plan: unlike `zone_gate_bands` (per-zone, corpus-wide OPEN borders),
    this keeps zones ISOLATED — each adjacent land-zone pair gets only 1..`max_entrances`
    narrow aligned crossings and the rest of the border is left to the vegetation sampler's
    border densification (pp_sample). Computed ONCE per level over ALL zones so both sides of
    a pair agree on where the crossing is:

      - entrance 1 sits at the front's centroid-nearest tile (the same rep math as
        `zone_gate_bands`), its far-side rep at the closest opposite-front tile;
      - a 2nd entrance only when the front is at least `long_front` tiles AND its rep (the
        front tile farthest from entrance 1) is >= `min_sep` Chebyshev away — long borders
        read badly with a single hole, short ones must stay single-entry;
      - each side's band = the `entrance_w` front tiles nearest its rep (protected from
        vegetation, so the crossing is guaranteed at least that wide).

    Returns {zid: [(rep, frozenset(band), other_zid), ...]} — the (rep, band) pairs are
    drop-in for every `zone_gate_bands` consumer. Pure geometry, rng-free, deterministic
    (all argmin/argmax tie-break on the tile tuple)."""
    fronts = _pair_fronts(zones)

    out: dict[int, list[Entrance]] = {zid: [] for zid in zones}
    for a, b in sorted(fronts):
        if a >= b:
            continue  # each unordered pair planned once
        Ta = sorted(fronts[(a, b)])
        Tb = sorted(fronts.get((b, a), ()))
        if not Ta or not Tb:
            continue
        reps = _pair_reps(Ta, Tb, long_front, max_entrances, min_sep)
        for ra, rb in reps[:max_entrances]:
            band_a = frozenset(
                sorted(Ta, key=lambda t: (max(abs(t[0] - ra[0]), abs(t[1] - ra[1])), t))[
                    :entrance_w
                ]
            )
            band_b = frozenset(
                sorted(Tb, key=lambda t: (max(abs(t[0] - rb[0]), abs(t[1] - rb[1])), t))[
                    :entrance_w
                ]
            )
            out[a].append(Entrance(ra, band_a, b))
            out[b].append(Entrance(rb, band_b, a))
    return out


def zone_gates(ts: Collection[Tile], zones: Mapping[int, Zone], zid: int) -> list[Tile]:
    """Passages (gates) through the rim belt -- the user's 'input and exit must correspond' rule.

    A blocked forest belt rings the zone, but a zone is not a sealed pocket: where it borders a
    DIFFERENT land zone there is a pass, and crucially an entry on one edge implies an exit on the
    far edge so the zone is TRAVERSABLE end-to-end (you can come in one side and leave the other).
    We return one representative tile per neighbouring zone (the centre of each contact segment).
    If the zone has fewer than two such neighbours (an isolated pocket), we synthesise an antipodal
    pair -- the two border tiles that are farthest apart -- so there is always a through-route. The
    spanning backbone then routes a corridor to every gate, punching the belt open exactly there."""
    contacts = zone_fronts(ts, zones, zid)
    gates: list[Tile] = []
    for tiles in contacts.values():
        mx = sum(t[0] for t in tiles) / len(tiles)
        my = sum(t[1] for t in tiles) / len(tiles)
        gates.append(min(set(tiles), key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2))
    if len(gates) < 2:
        border = [t for t in ts if any((t[0] + dx, t[1] + dy) not in ts for dx, dy in NB4)]
        if border:
            # farthest-apart border pair: farthest from centroid -> a, then farthest from a -> b
            mx = sum(x for x, _ in ts) / len(ts)
            my = sum(y for _, y in ts) / len(ts)
            a = max(border, key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2)
            b = max(border, key=lambda t: (t[0] - a[0]) ** 2 + (t[1] - a[1]) ** 2)
            for g in (a, b):
                if g not in gates:
                    gates.append(g)
    return gates
