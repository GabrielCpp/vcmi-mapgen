from vcmi_mapgen.core.steps.gameplay.siting import erode, owner


def test_the_first_player_to_arrive_owns_a_tile() -> None:
    assert owner((7, 4)) == 1
    assert owner((4, 4)) == 0
    assert owner((None, None)) is None


def test_a_tile_takes_the_worst_tier_within_reach() -> None:
    tiers = {(0, x, 0): (0, 0) for x in range(6)}
    tiers[0, 5, 0] = (1, 0)
    got = erode(tiers, 2)
    assert [got[0, x, 0] for x in range(6)] == [(0, 0)] * 3 + [(1, 0)] * 3


def test_erosion_stays_on_its_level() -> None:
    tiers = {(0, 0, 0): (0, 0), (1, 0, 0): (2, 0)}
    assert erode(tiers, 3)[0, 0, 0] == (0, 0)


def test_erosion_spreads_across_both_axes() -> None:
    tiers = {(0, x, y): (0, 1) for x in range(3) for y in range(3)}
    tiers[0, 2, 2] = (0, 2)
    assert erode(tiers, 1)[0, 1, 1] == (0, 2)
    assert erode(tiers, 1)[0, 0, 0] == (0, 1)
