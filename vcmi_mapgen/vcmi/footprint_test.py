from vcmi_mapgen.core.model import Footprint, Role
from vcmi_mapgen.vcmi.catalog.tables import leaf_meta
from vcmi_mapgen.vcmi.footprint import footprint_of, mask_rows, sealed


def test_decode_anchors_at_the_bottom_right() -> None:
    fp = footprint_of(("VB", "BX"))
    assert fp == Footprint(
        2,
        2,
        (
            (-1, -1, Role.OVERLAY),
            (0, -1, Role.BLOCKING),
            (-1, 0, Role.BLOCKING),
            (0, 0, Role.ENTRANCE),
        ),
    )


def test_every_ontology_mask_round_trips() -> None:
    for meta in leaf_meta().values():
        assert mask_rows(footprint_of(meta.mask)) == meta.mask


def test_sealing_turns_a_walk_on_cell_into_an_entrance() -> None:
    assert sealed(("VV", "VA")) == ("VV", "VX")


def test_sealing_turns_a_walk_on_cell_above_the_body_into_a_block() -> None:
    assert sealed(("AAA", "AAA")) == ("BBB", "XXX")


def test_sealing_leaves_a_mask_without_walk_on_cells_alone() -> None:
    assert sealed(("VB", "BX")) == ("VB", "BX")
