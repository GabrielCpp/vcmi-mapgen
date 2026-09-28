from vcmi_mapgen.vcmi.formats.vmap.terrain import vcmi_mask, visitable_from


def test_vcmi_mask_collapses_blocked_entrance_to_visitable() -> None:
    """This loses information on purpose -- see the docstring. Callers needing the
    internal charset must re-derive it from the ontology, never from this output."""
    assert vcmi_mask(["BBB", "BXB", "BBB"]) == ["BBB", "BAB", "BBB"]


def test_visitable_from_distinguishes_building_from_freestanding() -> None:
    assert visitable_from(["BBB", "BXB"]) == ["---", "+-+", "+++"]  # blocked body -> building
    assert visitable_from(["A"]) == ["+++", "+-+", "+++"]  # no blocked body
    assert visitable_from(["VVV", "VVV"]) is None  # pure decoration
