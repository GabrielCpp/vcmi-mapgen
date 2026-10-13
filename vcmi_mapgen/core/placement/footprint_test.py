from vcmi_mapgen.core.model import Footprint, Role
from vcmi_mapgen.core.placement.footprint import overlay_cells, room_offsets


def test_overlay_cells_are_the_cells_that_neither_block_nor_interact() -> None:
    fp = Footprint(
        2,
        2,
        (
            (-1, -1, Role.OVERLAY),
            (0, -1, Role.OVERLAY),
            (-1, 0, Role.BLOCKING),
            (0, 0, Role.ENTRANCE),
        ),
    )
    assert overlay_cells(fp, (5, 5)) == frozenset({(4, 4), (5, 4)})


def test_room_offsets_ring_the_body_and_its_approach() -> None:
    body = Footprint(1, 1, ((0, 0, Role.ENTRANCE),))
    assert set(room_offsets(body)) == {(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1, 2)}
