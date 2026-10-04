from vcmi_mapgen.vcmi.catalog.regen import themed_terrains

ALL = "111111111"


def test_a_type_with_several_native_masks_puts_each_template_on_its_native_land() -> None:
    records = [
        ("snowy", ALL, "000001000", 84, 0, ("B",)),
        ("sandy", ALL, "000000010", 84, 0, ("B",)),
        ("plain", ALL, "000000010", 63, 0, ("B",)),
    ]
    assert themed_terrains(records) == {"snowy": ["snow"], "sandy": ["sand"]}
