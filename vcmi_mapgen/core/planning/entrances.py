"""Zone-shape planning: entrance, gate and front geometry.
Shared by the gameplay, gated and vegetation steps' entrance and backbone logic."""

import collections
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.grid.geometry import NB4
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Entrance, Tile
from vcmi_mapgen.core.reading.borders import AdjacencyKind

ENTRANCE_W = 3  # entrance band width in front tiles per side (hero + guard fit through)
LONG_FRONT = 20  # a zone-pair front at least this long earns a second entrance
MAX_ENTRANCES = 2  # "a few" — hard cap on planned crossings per zone pair
MIN_ENTRANCE_SEP = 12  # Chebyshev floor between two entrances of the same pair
OPEN_FRAC = 0.5
MIN_W = 3


@dataclass(frozen=True, slots=True)
class Gate:
    """A passage through a zone's rim: `rep` is its one representative tile and `band` the
    front tiles kept open around it."""

    rep: Tile
    band: frozenset[Tile]


def _label_at(zone_label: ZoneLabel, x: int, y: int) -> int:
    if 0 <= y < len(zone_label) and 0 <= x < len(zone_label[y]):
        return zone_label[y][x]
    return -1


def zone_fronts(ts: Iterable[Tile], zone_label: ZoneLabel, zid: int) -> dict[int, list[Tile]]:
    """Full contact FRONTS: {neighbour zid: [zone tiles 4-touching that neighbour]}. The complete
    per-pair border segment — `zone_gates` collapses each front to one tile; `zone_gate_bands`
    keeps a corpus-wide band of it."""
    contacts: collections.defaultdict[int, list[Tile]] = collections.defaultdict(list)
    for x, y in ts:
        for dx, dy in NB4:
            o = _label_at(zone_label, x + dx, y + dy)
            if o >= 0 and o != zid:
                contacts[o].append((x, y))
    return contacts


def _front_gate(tiles: list[Tile], open_frac: float, min_w: int) -> Gate:
    mx = sum(t[0] for t in tiles) / len(tiles)
    my = sum(t[1] for t in tiles) / len(tiles)
    front = set(tiles)
    rep = min(front, key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2)
    k = min(len(front), max(min_w, round(open_frac * len(front))))
    band = sorted(front, key=lambda t: (max(abs(t[0] - rep[0]), abs(t[1] - rep[1])), t))[:k]
    return Gate(rep, frozenset(band))


def _antipodal_gates(ts: Collection[Tile], reps: Collection[Tile], min_w: int) -> list[Gate]:
    border = [t for t in ts if any((t[0] + dx, t[1] + dy) not in ts for dx, dy in NB4)]
    if not border:
        return []
    # farthest-apart border pair: farthest from centroid -> a, then farthest from a -> b
    mx = sum(x for x, _ in ts) / len(ts)
    my = sum(y for _, y in ts) / len(ts)
    a = max(border, key=lambda t: (t[0] - mx) ** 2 + (t[1] - my) ** 2)
    b = max(border, key=lambda t: (t[0] - a[0]) ** 2 + (t[1] - a[1]) ** 2)
    out: list[Gate] = []
    for g in (a, b):
        if g not in reps and all(g != o.rep for o in out):
            band = frozenset(
                t for t in border if max(abs(t[0] - g[0]), abs(t[1] - g[1])) <= min_w // 2
            )
            out.append(Gate(g, band | {g}))
    return out


def _zone_gates(
    ts: Collection[Tile], zone_label: ZoneLabel, zid: int, open_frac: float, min_w: int
) -> tuple[dict[int, Gate], list[Gate]]:
    contacts = zone_fronts(ts, zone_label, zid)
    fronts = {o: _front_gate(tiles, open_frac, min_w) for o, tiles in contacts.items()}
    if len(fronts) >= 2:
        return fronts, []
    return fronts, _antipodal_gates(ts, {g.rep for g in fronts.values()}, min_w)


def zone_gate_bands(
    ts: Collection[Tile],
    zone_label: ZoneLabel,
    zid: int,
    open_frac: float = OPEN_FRAC,
    min_w: int = MIN_W,
) -> list[Gate]:
    """Wide gates — corpus zone 'gates' are broad terrain borders, not 1-tile corridors.

    Returns one `Gate` per neighbouring zone, in zone-id order: `rep` is the single
    representative tile (identical to `zone_gates`) and `band` is the contact-front tiles
    around it — the corpus-like OPEN share of the front (`open_frac` = fraction of corpus
    zone-border tiles left passable, mined per terrain), never fewer than `min_w` tiles. The
    protected web keeps the whole band vegetation-free, so the border stays as open as real
    maps. Isolated pockets get the synthesized antipodal pair with a small border band each.
    The defaults `OPEN_FRAC` and `MIN_W` are hardcoded, not mined."""
    fronts, extra = _zone_gates(ts, zone_label, zid, open_frac, min_w)
    return [fronts[o] for o in sorted(fronts)] + extra


def _pair_fronts(zone_label: ZoneLabel) -> collections.defaultdict[tuple[int, int], set[Tile]]:
    fronts: collections.defaultdict[tuple[int, int], set[Tile]] = collections.defaultdict(
        set
    )  # ordered pair (a, b) -> a-side tiles
    for y, row in enumerate(zone_label):
        for x, zz in enumerate(row):
            if zz < 0:
                continue
            for dx, dy in NB4:
                o = _label_at(zone_label, x + dx, y + dy)
                if o >= 0 and o != zz:
                    fronts[(zz, o)].add((x, y))
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


@dataclass(frozen=True, slots=True)
class EntranceGeometry:
    entrance_w: int = ENTRANCE_W
    long_front: int = LONG_FRONT
    max_entrances: int = MAX_ENTRANCES
    min_sep: int = MIN_ENTRANCE_SEP


def _band(front: list[Tile], rep: Tile, width: int) -> frozenset[Tile]:
    return frozenset(
        sorted(front, key=lambda t: (max(abs(t[0] - rep[0]), abs(t[1] - rep[1])), t))[:width]
    )


def _gated(
    Ta: list[Tile], Tb: list[Tile], geometry: EntranceGeometry
) -> list[tuple[Tile, frozenset[Tile], Tile, frozenset[Tile]]]:
    g = geometry
    reps = _pair_reps(Ta, Tb, g.long_front, g.max_entrances, g.min_sep)
    return [
        (ra, _band(Ta, ra, g.entrance_w), rb, _band(Tb, rb, g.entrance_w))
        for ra, rb in reps[: g.max_entrances]
    ]


def _zids(zone_label: ZoneLabel) -> list[int]:
    return sorted({zz for row in zone_label for zz in row if zz >= 0})


def plan_entrances(
    zone_label: ZoneLabel,
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

    Returns {zid: [(rep, frozenset(band), other_zid), ...]} for every zone id in
    `zone_label`. Pure geometry, rng-free, deterministic (all argmin/argmax tie-break on the
    tile tuple)."""
    geometry = EntranceGeometry(entrance_w, long_front, max_entrances, min_sep)
    fronts = _pair_fronts(zone_label)

    out: dict[int, list[Entrance]] = {zid: [] for zid in _zids(zone_label)}
    for a, b in sorted(fronts):
        if a >= b:
            continue  # each unordered pair planned once
        Ta = sorted(fronts[(a, b)])
        Tb = sorted(fronts.get((b, a), ()))
        if not Ta or not Tb:
            continue
        for ra, band_a, rb, band_b in _gated(Ta, Tb, geometry):
            out[a].append(Entrance(ra, band_a, b))
            out[b].append(Entrance(rb, band_b, a))
    return out


@dataclass(frozen=True, slots=True)
class Passages:
    """One level's passage set, the only entrance plan the steps after the terrain read:
    each zone's entrances by zone id, both sides of a pair agreeing on where, and the zone
    pairs ``(a, b)``, ``a < b``, whose border is open."""

    entrances: Mapping[int, Sequence[Entrance]]
    open_pairs: frozenset[tuple[int, int]] = frozenset()


def all_passages(zone_label: ZoneLabel, entrance_w: int = ENTRANCE_W) -> Passages:
    """``plan_entrances`` over every touching pair, each band ``entrance_w`` front tiles
    wide, with no open pair."""
    return Passages(plan_entrances(zone_label, entrance_w))


def plan_passages(
    zone_label: ZoneLabel,
    kinds: Mapping[tuple[int, int], AdjacencyKind],
) -> Passages:
    """The passages of each touching pair by its kind in ``kinds``: across a gated border
    the entrances ``plan_entrances`` plans, across an open border one entrance whose band is
    the whole front on each side, and none across a closed border or a pair ``kinds`` leaves
    out."""
    fronts = _pair_fronts(zone_label)
    out: dict[int, list[Entrance]] = {zid: [] for zid in _zids(zone_label)}
    opened: set[tuple[int, int]] = set()
    for a, b in sorted(fronts):
        if a >= b or kinds.get((a, b), AdjacencyKind.CLOSED) == AdjacencyKind.CLOSED:
            continue
        Ta, Tb = sorted(fronts[(a, b)]), sorted(fronts.get((b, a), ()))
        if not Ta or not Tb:
            continue
        crossings = _gated(Ta, Tb, EntranceGeometry())
        if kinds[(a, b)] == AdjacencyKind.OPEN:
            ra, _ba, rb, _bb = crossings[0]
            crossings = [(ra, frozenset(Ta), rb, frozenset(Tb))]
            opened.add((a, b))
        for ra, band_a, rb, band_b in crossings:
            out[a].append(Entrance(ra, band_a, b))
            out[b].append(Entrance(rb, band_b, a))
    return Passages(out, frozenset(opened))


def zone_gates(ts: Collection[Tile], zone_label: ZoneLabel, zid: int) -> list[Tile]:
    """Passages (gates) through the rim belt -- the user's 'input and exit must correspond' rule.

    A blocked forest belt rings the zone, but a zone is not a sealed pocket: where it borders a
    DIFFERENT land zone there is a pass, and crucially an entry on one edge implies an exit on the
    far edge so the zone is TRAVERSABLE end-to-end (you can come in one side and leave the other).
    We return one representative tile per neighbouring zone (the centre of each contact segment),
    in the order `zone_fronts` found the neighbours. If the zone has fewer than two such
    neighbours (an isolated pocket), we synthesise an antipodal pair -- the two border tiles that
    are farthest apart -- so there is always a through-route. The spanning backbone then routes a
    corridor to every gate, punching the belt open exactly there."""
    fronts, extra = _zone_gates(ts, zone_label, zid, OPEN_FRAC, MIN_W)
    return [g.rep for g in [*fronts.values(), *extra]]
