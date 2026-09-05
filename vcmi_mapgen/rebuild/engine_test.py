from vcmi_mapgen.rebuild.engine import fm_to_document

_CELL = {"t": 2, "view": 0, "rt": 0, "rd": 0, "ot": 0, "od": 0, "m": 0}


def _fm(objects, main_town=None, width=5, height=5):
    return {
        "name": "fixture", "width": width, "height": height, "twoLevel": False,
        "main_town": main_town,
        "terrain": [[[dict(_CELL) for _ in range(width)] for _ in range(height)]],
        "objects": objects,
    }


def test_objects_without_a_resolved_type_are_dropped():
    fm = _fm([{"x": 1, "y": 1, "l": 0, "type": None, "subtype": None,
               "animation": "x", "mask": ["B"]}])
    doc = fm_to_document(fm)
    assert doc.objects == []


def test_start_town_is_wired_to_player_0():
    """fm['main_town'] must land on the alphabetically-first player color (blue), not
    just whichever town happens first in placement order."""
    towns = [
        {"x": 40, "y": 40, "l": 0, "type": "randomTown", "subtype": "0",
         "animation": "avctowx0", "mask": ["B"]},
        {"x": 10, "y": 10, "l": 0, "type": "randomTown", "subtype": "0",
         "animation": "avctowx0", "mask": ["B"]},
    ]
    fm = _fm(towns, main_town={"l": 0, "x": 10 - 2, "y": 10 - 2}, width=60, height=60)
    doc = fm_to_document(fm)

    blue = doc.player("blue")
    assert blue.can_play == "PlayerOrAI"
    assert blue.main_town == {"generateHero": True, "l": 0, "x": 8, "y": 8}

    green = doc.player("green")
    assert green.can_play == "PlayerOrAI"
    assert green.main_town == {"generateHero": True, "l": 0, "x": 38, "y": 38}

    # every other slot stays a non-participant
    for color in ("orange", "pink", "purple", "red", "tan", "teal"):
        pl = doc.player(color)
        assert pl.can_play == "false"
        assert pl.main_town is None


def test_same_as_town_marker_resolves_to_the_towns_instance_name():
    town = {"x": 20, "y": 20, "l": 0, "type": "town", "subtype": "castle",
            "animation": "avctowx0", "mask": ["B"]}
    dwelling = {"x": 5, "y": 5, "l": 0, "type": "dwelling", "subtype": "0",
                "animation": "avldwlx0", "mask": ["B"],
                "options": {"sameAsTown": [20, 20, 0]}}
    fm = _fm([town, dwelling])
    doc = fm_to_document(fm)

    by_pos = {(o.x, o.y): o for o in doc.objects}
    town_vo = by_pos[(20, 20)]
    dwelling_vo = by_pos[(5, 5)]
    assert dwelling_vo.options["sameAsTown"] == town_vo.instance_name


def test_same_as_town_marker_is_dropped_when_its_town_is_gone():
    dwelling = {"x": 5, "y": 5, "l": 0, "type": "dwelling", "subtype": "0",
                "animation": "avldwlx0", "mask": ["B"],
                "options": {"sameAsTown": [99, 99, 0]}}
    fm = _fm([dwelling])
    doc = fm_to_document(fm)
    assert doc.objects[0].options is None
