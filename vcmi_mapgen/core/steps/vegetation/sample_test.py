"""Reliability tests for steps.vegetation.sample (marked-point-process vegetation sampler)."""

import os

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.geometry import edge_dist
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.planning.entrances import plan_entrances, zone_fronts, zone_gate_bands
from vcmi_mapgen.core.steps.vegetation import sample as PP
from vcmi_mapgen.corpus.vegetation import PP_DIR


def _zone(ts: set[Tile], cx: float, cy: float, terrain_type: int = 2) -> Zone:
    return Zone(
        terrain_type=Terrain(terrain_type),
        area=len(ts),
        centroid=(cx, cy),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


HAVE_STATS = os.path.exists(os.path.join(PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


@needs_stats
def test_model_and_sampler_deterministic(catalog: Catalog) -> None:
    model = PP.build_model(catalog, "grass")
    assert model.cats, "grass model has categories"
    assert 0 < model.target < 1
    ts = {(x, y) for x in range(18) for y in range(14)}
    ref = PP.ZoneRef(ts, label_zones({1: _zone(ts, 8.5, 6.5)}), 1, (8.5, 6.5))
    a1, b1, _ = PP.sample_zone(ref, model, seed=5)
    a2, b2, _ = PP.sample_zone(ref, model, seed=5)
    assert a1 == a2 and b1 == b2, "same seed must reproduce bit-exactly"
    assert a1, "some vegetation sampled"
    # every mask comes from the catalog and coverage is sane
    for o in a1:
        assert catalog.spec(o.animation) is not None
    assert 0.1 < len(b1) / len(ts) < 0.95


@needs_stats
def test_protected_web_stays_open(catalog: Catalog) -> None:
    """No blocking cell may land on the protected walkable web (the hard zero)."""
    model = PP.build_model(catalog, "grass")
    ts = {(x, y) for x in range(20) for y in range(16)}
    ref = PP.ZoneRef(ts, label_zones({1: _zone(ts, 9.5, 7.5)}), 1, (9.5, 7.5))
    objs, blocked, prot = PP.sample_zone(ref, model, seed=9)
    assert prot, "web exists"
    for o in objs:
        for cx, cy, blk in FP.anchored_cells(o.footprint, o.x, o.y):
            if blk:
                assert (cx, cy) not in prot
    assert not (blocked & prot)


@needs_stats
def test_protected_web_covers_gate_bands() -> None:
    ts1 = {(x, y) for x in range(14) for y in range(12)}
    ts2 = {(x, y) for x in range(14, 28) for y in range(12)}
    label = label_zones({1: _zone(ts1, 6.5, 5.5), 2: _zone(ts2, 20.5, 5.5, 3)})
    edist = edge_dist(ts1)
    ref = PP.ZoneRef(ts1, label, 1, (6.5, 5.5))
    prot = PP.protected_web(ref, edist, (6, 5), PP.WebOptions(open_frac=0.5))
    for g in zone_gate_bands(ts1, label, 1, open_frac=0.5):
        assert g.band <= prot, "every gate-band tile must be protected from vegetation"


@needs_stats
def test_border_bias_densifies_front(catalog: Catalog) -> None:
    """Zone isolation: with BOTH zones sampling under the `border=` bias, the aligned
    open crossings outside the planned entrance band shrink. Each single side is only a
    partial ridge (Geyer saturation caps clumping), so the border plan closes the rest."""
    ts1 = {(x, y) for x in range(14) for y in range(12)}
    ts2 = {(x, y) for x in range(14, 28) for y in range(12)}
    zones = {1: _zone(ts1, 6.5, 5.5), 2: _zone(ts2, 20.5, 5.5, 2)}
    label = label_zones(zones)
    plan = plan_entrances(label)
    model = PP.build_model(catalog, "grass")

    def zone_pass(
        zid: int, ts: set[Tile], seed: int, border_bias: bool = True
    ) -> tuple[frozenset[Tile] | set[Tile], set[Tile], set[Tile], frozenset[Tile]]:
        z_entr = plan[zid]
        edist = edge_dist(ts)
        c = zones[zid].centroid
        seedt = min(ts, key=lambda t: (t[0] - round(c[0])) ** 2 + (t[1] - round(c[1])) ** 2)
        prot = PP.protected_web(
            PP.ZoneRef(ts, label, zid, c), edist, seedt, PP.WebOptions(entrances=z_entr)
        )
        front = {t for tiles in zone_fronts(ts, label, zid).values() for t in tiles}
        bands = {t for _r, b, _o in z_entr for t in b}
        border = frozenset(front - bands) if border_bias else frozenset[Tile]()
        _, blk, _ = PP.sample_zone(
            PP.ZoneRef(ts, label, zid, c),
            model,
            seed=seed,
            opts=PP.SampleOptions(prot=prot, border=border),
        )
        return blk, front, bands, frozenset(front - bands)

    for seed in (3, 7):
        blk1, f1, b1, border1 = zone_pass(1, ts1, seed)
        blk2, _f2, b2, _ = zone_pass(2, ts2, seed)
        assert not (blk1 & b1) and not (blk2 & b2), "entrance bands stay vegetation-free"
        open_all = (ts1 - blk1) | (ts2 - blk2)
        crossings = {t for t in f1 if t in open_all and (t[0] + 1, t[1]) in open_all}
        assert crossings, "the planned entrance must stay open"
        plain1, *_ = zone_pass(1, ts1, seed, border_bias=False)
        plain2, *_ = zone_pass(2, ts2, seed, border_bias=False)
        plain_open = (ts1 - plain1) | (ts2 - plain2)
        plain_cross = {t for t in f1 if t in plain_open and (t[0] + 1, t[1]) in plain_open}
        assert len(crossings - b1) < len(plain_cross - b1), "the bias must close crossings"
        # the bias densifies the front vs the unbiased sampler on the same seed
        blk_plain, *_ = zone_pass(1, ts1, seed, border_bias=False)
        assert len(blk1 & border1) > len(blk_plain & border1), "border bias must densify the front"
        # coverage correction keeps TOTAL density corpus-like (redistribution, not inflation)
        assert len(blk1) / len(ts1) < model.target + 0.2
