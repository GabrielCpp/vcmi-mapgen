from vcmi_mapgen.renderers.territories import PX, render_territories


def test_the_image_is_ten_pixels_per_tile_and_territories_differ() -> None:
    label = [[0, 0, 1, 1] for _ in range(4)]
    img = render_territories(label, {0: 0, 1: 1}, [None, None], [], [])
    assert img.size == (4 * PX, 4 * PX)
    assert img.getpixel((PX // 2, PX // 2)) != img.getpixel((3 * PX + PX // 2, PX // 2))


def test_water_doors_and_homes_are_drawn() -> None:
    label = [[0, 0, 1, -1] for _ in range(4)]
    img = render_territories(label, {0: 0, 1: 1}, [0, None], [(1, 1)], [(0, 3)])
    assert img.getpixel((3 * PX + 5, 5)) == (10, 20, 90)
    assert img.getpixel((1 * PX + 5, 1 * PX + 5)) == (255, 255, 255)
    assert img.getpixel((0 * PX + 5, 3 * PX + 5)) == (0, 0, 0)
    assert img.getpixel((5, 5)) != img.getpixel((2 * PX + 5, 5))
