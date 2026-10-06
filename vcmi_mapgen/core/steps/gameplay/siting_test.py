from vcmi_mapgen.core.steps.gameplay.siting import owner


def test_the_first_player_to_arrive_owns_a_tile() -> None:
    assert owner((7, 4)) == 1
    assert owner((4, 4)) == 0
    assert owner((None, None)) is None
