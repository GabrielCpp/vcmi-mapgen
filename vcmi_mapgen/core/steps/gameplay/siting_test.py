import random
from types import SimpleNamespace
from typing import ClassVar, cast, final, override

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.reading.families import dwelling_family, family_purpose
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.pick import Pick, Picker
from vcmi_mapgen.core.steps.gameplay.reach import Reach
from vcmi_mapgen.core.steps.gameplay.siting import (
    Codes,
    Group,
    Shape,
    Siting,
    Tier,
    TileGrid,
    Tiles,
    owner,
)


def test_the_first_player_to_arrive_owns_a_tile() -> None:
    assert owner((7, 4)) == 1
    assert owner((4, 4)) == 0
    assert owner((None, None)) is None


def _worst(rows: list[str], r: int) -> list[str]:
    """Each tile of the one-level ASCII ``rows`` replaced by the worst code within ``r`` of it,
    a digit a tile with that code and ``.`` no tile."""
    cells = [(y, x, c) for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."]
    grid = TileGrid(
        (1, len(rows), max(len(r) for r in rows)),
        (
            np.zeros(len(cells), dtype=np.intp),
            np.array([y for y, _x, _c in cells], dtype=np.intp),
            np.array([x for _y, x, _c in cells], dtype=np.intp),
        ),
    )
    values: Codes = np.array([int(c) for _y, _x, c in cells], dtype=np.int64)
    got = iter(cast(list[int], grid.worst_within(values, r).tolist()))
    return ["".join(c if c == "." else str(next(got)) for c in row) for row in rows]


def test_a_tile_takes_the_worst_code_within_reach() -> None:
    assert _worst(["000001"], 2) == ["000111"]


def test_the_worst_code_spreads_across_both_axes() -> None:
    assert _worst(["111", "111", "112"], 1) == ["111", "122", "122"]


def test_a_gap_in_the_grid_does_not_stop_the_reach() -> None:
    assert _worst(["0.3"], 2) == ["3.3"]


def test_two_levels_never_mix() -> None:
    grid = TileGrid(
        (2, 1, 1),
        (
            np.array([0, 1], dtype=np.intp),
            np.array([0, 0], dtype=np.intp),
            np.array([0, 0], dtype=np.intp),
        ),
    )
    assert grid.worst_within(np.array([0, 2]), 3).tolist() == [0, 2]


class _Site:
    zid: int = 0


class _Spy(Siting):
    asked: ClassVar[list[object]] = []

    @override
    def _parts(
        self,
        dealt: str,
        site: ZoneSite,
        rows: NDArray[np.intp],
        seen: object,
        strict: bool,
    ) -> list[tuple[str, Pick, NDArray[np.intp]]]:
        self.asked.append(site)
        return []


def test_a_site_with_no_cap_left_gets_no_capped_object() -> None:
    full, open_ = cast(ZoneSite, cast(object, _Site())), cast(ZoneSite, cast(object, _Site()))
    spy = _Spy(
        [full, open_],
        cast(Picker, cast(object, None)),
        lambda d: d,
        random.Random(0),
        Reach(0),
        tiles=_ranked_siting([]).tiles,
    )
    spy.caps = {0: 0, 1: 1}
    spy.capped = frozenset({Purpose.DWELLING})
    tier: Tier = (0, 0, 0)
    groups: list[Group] = [
        (tier, full, np.zeros(1, dtype=np.intp)),
        (tier, open_, np.zeros(1, dtype=np.intp)),
    ]
    spy._pool = groups  # pyright: ignore[reportPrivateUsage]
    family = dwelling_family(1)
    assert family_purpose(family) == Purpose.DWELLING
    _spy_asked = _Spy.asked
    _spy_asked.clear()
    assert spy._stand(family, groups, ({}, None), False) is None  # pyright: ignore[reportPrivateUsage]
    assert open_ in _spy_asked
    assert full not in _spy_asked


@final
class _Zoned:
    def __init__(self, zid: int) -> None:
        self.zid = zid
        self.lf = SimpleNamespace(level=0)


@final
class _Walk(Siting):
    @override
    def _parts(
        self,
        dealt: str,
        site: ZoneSite,
        rows: NDArray[np.intp],
        seen: object,
        strict: bool,
    ) -> list[tuple[str, Pick, NDArray[np.intp]]]:
        if site.zid == 7:
            return []
        return [(dealt, cast(Pick, cast(object, None)), rows)]

    @override
    def _try(
        self,
        family: str,
        site: ZoneSite,
        centres: list[Tile],
        pick: Pick,
        how: tuple[bool, Shape, int],
    ) -> PlacedObject | None:
        self._centre = (0, centres[1])
        return cast(PlacedObject, cast(object, SimpleNamespace(x=8, y=0)))


def _ranked_siting(sites: list[ZoneSite], cls: type[Siting] = Siting) -> Siting:
    keys = [(0, x, 0) for x in range(12)]
    tiles = Tiles(
        keys,
        np.array([0] * 6 + [1] * 6, dtype=np.intp),
        np.zeros((1, 12, 1), dtype=np.int64),
        TileGrid((1, 1, 12), (np.zeros(12, np.intp), np.zeros(12, np.intp), np.arange(12))),
    )
    return cls(
        sites,
        cast(Picker, cast(object, None)),
        lambda d: d,
        random.Random(0),
        Reach(0),
        tiles=tiles,
    )


def _two_groups() -> tuple[list[ZoneSite], list[Group], tuple[Codes, Codes]]:
    near, far = cast(ZoneSite, cast(object, _Zoned(7))), cast(ZoneSite, cast(object, _Zoned(9)))
    tier: Tier = (0, 0, 0)
    groups: list[Group] = [(tier, near, np.arange(0, 6)), (tier, far, np.arange(6, 12))]
    return [near, far], groups, (np.arange(12, dtype=np.int64) * 10, np.arange(12, dtype=np.int64))


def test_a_slot_with_nothing_standing_records_the_tiles_of_its_first_group() -> None:
    sites, groups, cols = _two_groups()
    siting = _ranked_siting(sites)
    _ = siting.note(groups, ("spread", "arrival"), cols)
    siting.record(Slot("MINE:y"), 0, None)
    (only,) = siting.ranking
    assert only.keys == ("spread", "arrival")
    assert [(t.x, t.zid) for t in only.ranked] == [(x, 7) for x in range(6)]
    assert only.ranked[1].values == (10, 1)
    assert only.stood is None


def test_a_slot_records_the_groups_it_walked_and_ranks_the_group_it_stood_in() -> None:
    sites, groups, cols = _two_groups()
    siting = _ranked_siting(sites, _Walk)
    _ = siting.note(groups, ("spread", "arrival"), cols)
    siting._pool = groups  # pyright: ignore[reportPrivateUsage]
    assert siting._stand("MINE:x", groups, ({}, None), False) is not None  # pyright: ignore[reportPrivateUsage]
    slot = Slot("MINE:x", 0, 1, 2)
    siting.record(slot, 1, siting._stood)  # pyright: ignore[reportPrivateUsage]
    (got,) = siting.ranking
    assert [(g.index, g.zid, g.size, g.outcome) for g in got.groups] == [
        (0, 7, 6, "no_object"),
        (1, 9, 6, "stood"),
    ]
    assert got.groups[1].values == (60, 6)
    assert got.groups_seen == 2
    assert [(t.x, t.zid) for t in got.ranked] == [(x, 9) for x in range(6, 12)]
    stood = got.stood
    assert stood is not None
    assert (stood.group, stood.centre, stood.rank, stood.tried_at) == (1, (7, 0), 1, 0)
