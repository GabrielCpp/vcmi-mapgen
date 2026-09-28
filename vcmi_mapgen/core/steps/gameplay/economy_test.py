"""Reliability tests for the zone economy ledger."""

import os

import pytest

from vcmi_mapgen.conftest import OpenZone, OpenZonePlacer
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, Ledger
from vcmi_mapgen.corpus.gameplay import STATS_PATH
from vcmi_mapgen.corpus.vegetation import PP_DIR

HAVE_STATS = os.path.exists(os.path.join(PP_DIR, "veg_grass.json"))
needs_stats = pytest.mark.skipif(not HAVE_STATS, reason="data/pp stats not mined")


@needs_stats
def test_mine_ledger_covers_basics_and_rations_gold(open_zone: OpenZonePlacer) -> None:
    """The map-level ledger drives zones to cover all six basic resources and blocks gold
    mines until the map holds several towns."""

    if not os.path.exists(STATS_PATH):
        pytest.skip("gameplay stats not mined")
    ts = {(x, y) for x in range(40) for y in range(30)}
    # gold is rationed to towns - 1 (a zone may roll a neutral town of its own, which
    # legitimately raises the quota — the INVARIANT is what must hold)
    for seed in range(1, 8):
        ledger = Ledger(missing=set(BASIC_MINE_RES), towns=1, gold=0)
        objs = open_zone(OpenZone(ts, "grass"), seed, ledger=ledger).gobjs
        n_gold = sum(1 for o in objs if o.purpose == Purpose.MINE and o.subtype == "goldMine")
        assert n_gold <= ledger.gold <= max(0, ledger.towns - 1), (
            f"seed {seed}: gold {n_gold} exceeds quota (towns={ledger.towns})"
        )
    # missing basics are drawn FIRST: a fresh ledger shrinks by every mine the zone placed
    ledger = Ledger(missing=set(BASIC_MINE_RES), towns=1, gold=0)
    objs = open_zone(OpenZone(ts, "grass"), 3, ledger=ledger).gobjs
    n_mines = sum(1 for o in objs if o.purpose == Purpose.MINE)
    assert len(ledger.missing) <= max(0, len(BASIC_MINE_RES) - n_mines), (
        "every placed mine must come from the missing set while it is non-empty"
    )
