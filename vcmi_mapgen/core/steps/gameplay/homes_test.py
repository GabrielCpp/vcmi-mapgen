from vcmi_mapgen.core.steps.gameplay.conftest import TownAt
from vcmi_mapgen.core.steps.gameplay.homes import player_towns


def test_a_moved_town_starts_a_player_before_a_guarded_neutral_town(town_at: TownAt) -> None:
    home_a, home_b, home_c = (
        town_at(10, 10),
        town_at(100, 10),
        town_at(10, 100),
    )
    neutral, moved = town_at(41, 87), town_at(70, 70)
    zids = [(0, 1), (0, 2), (0, 3), (0, 31)]
    homes = {(0, 1): home_a, (0, 2): home_b, (0, 3): home_c}
    towns = {
        (0, 1): [home_a],
        (0, 2): [home_b],
        (0, 3): [home_c],
        (0, 16): [neutral],
        (0, 95): [moved],
    }
    assert player_towns(homes, zids, [moved], towns, 4) == [home_a, home_b, home_c, moved]


def test_a_spare_town_tops_up_only_when_the_move_failed(town_at: TownAt) -> None:
    home, neutral = town_at(10, 10), town_at(41, 87)
    towns = {(0, 1): [home], (0, 16): [neutral]}
    assert player_towns({(0, 1): home}, [(0, 1), (0, 31)], [], towns, 2) == [home, neutral]
