from vcmi_mapgen.core.reading.claimed import Claim, claimed, worst_share

TABLE = [
    Claim(1000, (2, 6)),
    Claim(3000, (8, 3)),
    Claim(500, (4, 4)),
    Claim(9000, (30, None)),
    Claim(7000, (None, None)),
]


def test_the_first_player_to_arrive_claims_the_value() -> None:
    assert claimed(TABLE, 10) == (1500, 3500)


def test_a_reward_past_the_horizon_counts_for_nobody() -> None:
    assert claimed(TABLE, 3) == (1000, 3000)
    assert claimed(TABLE, 40) == (10500, 3500)


def test_a_tie_counts_for_both_players() -> None:
    assert claimed([Claim(500, (4, 4))], 5) == (500, 500)


def test_the_worst_share_is_the_worst_over_the_best() -> None:
    assert worst_share(TABLE, 10) == 1500 / 3500


def test_no_claim_gives_no_share() -> None:
    assert worst_share(TABLE, 1) is None
    assert worst_share([], 10) is None
