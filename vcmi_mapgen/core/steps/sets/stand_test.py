import random

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.sets.deal import Deal
from vcmi_mapgen.core.steps.sets.slots import Slot
from vcmi_mapgen.core.steps.sets.stand import Board, stand_all, stand_deal


def _ready(catalog: Catalog) -> tuple[str, ...]:
    ring = [s for s in catalog.artifact_sets() if s.name == "ringOfTheMagi"]
    if not ring or any(catalog.artifact(p) is None for p in ring[0].parts):
        pytest.skip("no VCMI install")
    return ring[0].parts


def _deal(catalog: Catalog, parts: tuple[str, ...]) -> tuple[Deal, list[HeldPrize]]:
    fallback = catalog.artifact(parts[0])
    assert fallback is not None
    held = [HeldPrize(0, (4 * i + 2, 3), "grass", fallback) for i in range(len(parts))]
    deal = Deal(
        "ringOfTheMagi", tuple((Slot(h, 4, 30, 0), p) for h, p in zip(held, parts, strict=True))
    )
    return deal, held


def test_a_set_stands_whole(catalog: Catalog, priors: Priors) -> None:
    parts = _ready(catalog)
    deal, held = _deal(catalog, parts)
    board = Board({0: CoverIndex()}, priors.gameplay[0], (16, 8))
    stood = stand_all(catalog, board, [deal], held, random.Random(1))
    [(dealt, objs)] = stood.sets
    assert dealt.name == "ringOfTheMagi"
    assert sorted(o.kind for o in objs) == sorted(
        i.kind for p in parts if (i := catalog.artifact(p)) is not None
    )
    assert stood.fallbacks == []


def test_a_set_with_one_blocked_slot_stands_nowhere(catalog: Catalog, priors: Priors) -> None:
    parts = _ready(catalog)
    deal, held = _deal(catalog, parts)
    cover = CoverIndex(claims={held[-1].tile})
    board = Board({0: cover}, priors.gameplay[0], (16, 8))
    assert stand_deal(catalog, board, deal, random.Random(1)) is None
    assert cover.claims == {held[-1].tile}
    stood = stand_all(catalog, board, [deal], held, random.Random(1))
    assert stood.sets == []
    assert sum(o is not None for o in stood.fallbacks) == len(parts) - 1
