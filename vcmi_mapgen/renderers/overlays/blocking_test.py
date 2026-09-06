from vcmi_mapgen.pipeline import MapState
from vcmi_mapgen.renderers.overlays.blocking import BlockingOverlay

TILE = 32


def _cell(t=2):
    return {"t": t, "view": 0, "rt": 0, "rd": 0, "ot": 0, "od": 0, "m": 0}


def _color_at(img, x, y):
    return img.getpixel((x * TILE, y * TILE))


def test_tiers_false_tints_every_blocking_cell_uniformly():
    grid = [[_cell() for _ in range(5)] for _ in range(5)]
    town = {"x": 3, "y": 3, "l": 0, "purpose": "TOWN",
            "template": {"mask": ["BB", "BA"]}}
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[town])
    img = BlockingOverlay(tiers=False).apply(state, 0)
    # 'B' cells anchored bottom-right at (3,3): (2,2),(3,2),(2,3) block; (3,3) is 'A'
    for x, y in ((2, 2), (3, 2), (2, 3)):
        assert _color_at(img, x, y)[3] > 0, f"({x},{y}) should be tinted"
    assert _color_at(img, 3, 3)[3] == 0, "the visit tile itself is not a blocking cell"


def test_tiers_true_separates_structure_body_from_visit_tile():
    grid = [[_cell() for _ in range(5)] for _ in range(5)]
    town = {"x": 3, "y": 3, "l": 0, "purpose": "TOWN", "mask": ["BB", "BA"]}
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[town])
    img = BlockingOverlay(tiers=True).apply(state, 0)

    body_color = _color_at(img, 2, 2)     # a 'B' body cell
    visit_color = _color_at(img, 3, 3)    # the 'A' visit cell
    assert body_color[3] > 0 and visit_color[3] > 0
    assert body_color != visit_color, "body and visit tiles must use different tiers"


def test_tiers_true_gives_solo_visit_its_own_tier():
    grid = [[_cell() for _ in range(5)] for _ in range(5)]
    shrine = {"x": 2, "y": 2, "l": 0, "purpose": "INFO", "mask": ["A"]}
    town = {"x": 4, "y": 4, "l": 0, "purpose": "TOWN", "mask": ["BB", "BA"]}
    state = MapState(cells={0: grid}, surfs={0: grid}, objs=[shrine, town])
    img = BlockingOverlay(tiers=True).apply(state, 0)

    solo_color = _color_at(img, 2, 2)
    struct_visit_color = _color_at(img, 4, 4)
    assert solo_color[3] > 0
    assert solo_color != struct_visit_color
