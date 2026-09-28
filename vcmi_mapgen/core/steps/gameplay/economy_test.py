"""Reliability tests for the zone economy ledger."""

from vcmi_mapgen.conftest import OpenZone, OpenZonePlacer
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, Ledger


def test_mine_ledger_covers_basics_and_rations_gold(open_zone: OpenZonePlacer) -> None:
    """The map-level ledger drives zones to cover all six basic resources and blocks gold
    mines until the map holds several towns."""
    ts = {(x, y) for x in range(40) for y in range(30)}
    # gold is rationed to towns - 1 (a zone may roll a neutral town of its own, which
    # legitimately raises the quota — the INVARIANT is what must hold)
    for seed in range(1, 8):
        ledger = Ledger(missing=set(BASIC_MINE_RES), towns=1, gold=0)
        objs = open_zone(OpenZone(ts, "grass"), seed, ledger=ledger).objs
        n_gold = sum(
            1
            for o in objs
            if o.purpose == Purpose.MINE
            and open_zone.catalog.identity_of(o.kind).subtype == "goldMine"
        )
        assert n_gold <= ledger.gold <= max(0, ledger.towns - 1), (
            f"seed {seed}: gold {n_gold} exceeds quota (towns={ledger.towns})"
        )
    # missing basics are drawn FIRST: a fresh ledger shrinks by every mine the zone placed
    ledger = Ledger(missing=set(BASIC_MINE_RES), towns=1, gold=0)
    objs = open_zone(OpenZone(ts, "grass"), 3, ledger=ledger).objs
    n_mines = sum(1 for o in objs if o.purpose == Purpose.MINE)
    assert len(ledger.missing) <= max(0, len(BASIC_MINE_RES) - n_mines), (
        "every placed mine must come from the missing set while it is non-empty"
    )
