"""The protected walkable web of one zone: a spanning backbone over farthest-point nodes
plus its rim gate bands. The zone plan and the vegetation sampler both keep it free of
blocking objects."""

from collections.abc import Collection, Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.grid.paths import SPACING, farthest_points, geodesic_path
from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.entrances import Gate, zone_fronts, zone_gate_bands

_NO_TILES: frozenset[Tile] = frozenset()


def _band_component(rep: Tile, band: AbstractSet[Tile]) -> set[Tile]:
    """The 4-connected part of `band` containing `rep`. A diagonal-only band tile would be
    a protected fragment that no walkable path reaches."""
    if rep not in band:
        return set()
    comp = {rep}
    stack = [rep]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in band and n not in comp:
                comp.add(n)
                stack.append(n)
    return comp


@dataclass(frozen=True, slots=True)
class ZoneRef:
    ts: AbstractSet[Tile]
    zone_label: ZoneLabel
    zid: int
    centroid: tuple[float, float]
    level: int = 0


@dataclass(frozen=True, slots=True)
class WebOptions:
    spacing: int = SPACING
    extra_nodes: Iterable[Tile] = ()
    avoid: Collection[Tile] = _NO_TILES
    open_frac: float = 0.5
    entrances: Iterable[tuple[Tile, frozenset[Tile], int]] | None = None
    keep_off: Collection[Tile] = _NO_TILES


_DEFAULT_WEB = WebOptions()


def protected_web(
    zone: ZoneRef,
    edist: Mapping[Tile, int],
    seedt: Tile,
    opts: WebOptions = _DEFAULT_WEB,
) -> set[Tile]:
    """The PROTECTED walkable set: spanning backbone over farthest-point nodes + rim gate
    BANDS (constructive global connectivity, reusing core.planning.entrances's helpers — spec §5).

    Gates are corpus-wide bands of the zone-contact front (`open_frac` = the mined fraction
    of corpus zone-border tiles left passable): the whole band is protected, so vegetation
    can never wall a border down to a 1-tile corridor — generated borders stay as open as
    real corpus borders. `extra_nodes` are mandatory destinations (gameplay approach tiles —
    every placed object stays reachable); `avoid` tiles (gameplay footprints) are
    impassable, so corridors route AROUND towns/mines instead of through them.

    `entrances` (this zone's `core.planning.entrances.plan_entrances` entries) switches
    the border model from corpus-open to ISOLATED: only the planned narrow entrance bands are
    protected — the rest of the front is left plantable, and `sample_zone`'s border bias
    actively densifies it (the map-level isolation redesign). `keep_off` (the caller's 8-connected
    rim: every tile with an 8-neighbour in another zone) further restricts backbone
    ROUTING in that mode — a web corridor pinned to the rim would both hold the ridge open
    and be unsealable by `pp_map.seal_zone_borders`."""
    ts, zone_label, zid = zone.ts, zone.zone_label, zone.zid
    avoid, keep_off, entrances = opts.avoid, opts.keep_off, opts.entrances
    ts_free = ts - set(avoid)
    if seedt not in ts_free:
        seedt = min(ts_free, key=lambda t: (t[0] - seedt[0]) ** 2 + (t[1] - seedt[1]) ** 2)
    gate_bands: list[Gate]
    if entrances is not None:
        gate_bands = [Gate(rep, band) for rep, band, _other in entrances]
        # keep the backbone OFF the non-entrance front/rim: a path hugging the border would
        # hold a protected walkable lane exactly where the border bias is trying to grow
        # the isolation ridge. Entrance bands stay in the routing domain (a rep is reached
        # through its own band); fall back to the full zone if a node is only reachable
        # along the front.
        fronts = zone_fronts(ts, zone_label, zid)
        front = {t for tiles in fronts.values() for t in tiles}
        band_all = {t for g in gate_bands for t in g.band}
        path_ts = ts_free - ((front | set(keep_off)) - band_all)
    else:
        gate_bands = zone_gate_bands(ts, zone_label, zid, open_frac=opts.open_frac)
        path_ts = ts_free
    gates = [g.rep for g in gate_bands]
    interior = [t for t in ts_free if edist.get(t, 0) >= 2] or list(ts_free)
    nodes = farthest_points(ts_free, seedt, opts.spacing, cand=interior)
    for g in list(gates) + [n for n in opts.extra_nodes if n in ts_free]:
        if g in ts_free and g not in nodes:
            nodes.append(g)
    prot = {seedt}
    connected = [seedt]
    remaining = [n for n in nodes if n != seedt]
    while remaining:
        best_r: Tile = remaining[0]
        best_c: Tile = connected[0]
        bd = 1 << 60
        for r in remaining:
            for c in connected:
                d = (r[0] - c[0]) ** 2 + (r[1] - c[1]) ** 2
                if d < bd:
                    bd, best_r, best_c = d, r, c
        path = (
            geodesic_path(best_c, best_r, path_ts)
            or geodesic_path(best_c, best_r, ts_free)
            or geodesic_path(best_c, best_r, ts)
        )
        prot.update(path)
        connected.append(best_r)
        remaining.remove(best_r)
    for g in gate_bands:
        prot.update(_band_component(g.rep, g.band & ts_free))
    return prot - set(avoid)
