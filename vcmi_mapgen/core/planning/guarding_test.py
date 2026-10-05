import random

from vcmi_mapgen.core.planning.content import ContentPlan, PlaceIntent
from vcmi_mapgen.core.planning.guarding import EVERY_LEVEL, GuardReading, prize_guard
from vcmi_mapgen.core.priors.places import PlaceContent, PlaceStats

ROWS = (
    PlaceContent("home", 0, 400, 4, 40000, (1, 2)),
    PlaceContent("middle", 1, 400, 4, 40000, (3,)),
    PlaceContent("treasure", 5, 100, 2, 50000, (6, 7)),
    PlaceContent("treasure", 6, 100, 2, 50000, (5,)),
)


def test_the_spread_pools_the_guards_seen_at_each_hop() -> None:
    reading = GuardReading.of(ROWS)
    assert reading.spread(0) == (1, 2)
    assert reading.spread(1) == (3,)
    assert reading.spread(4) == (5, 6, 7)
    assert reading.spread(9) == (5, 6, 7)


def test_an_unseen_or_unknown_hop_falls_back_to_the_whole_level() -> None:
    reading = GuardReading.of(ROWS)
    assert reading.spread(2) == (1, 2, 3, 5, 6, 7)
    assert reading.spread(None) == (1, 2, 3, 5, 6, 7)


def test_a_level_without_corpus_guards_draws_every_level() -> None:
    assert GuardReading.of(()).spread(3) == EVERY_LEVEL


def test_the_prize_guard_reads_the_hops_of_its_own_level() -> None:
    plan = ContentPlan(
        intents={
            (0, 4): PlaceIntent("treasure", 5, 1.0, 6.0),
            (0, 7): PlaceIntent("middle", 1, 1.0, 3.0),
            (1, 4): PlaceIntent("middle", 0, 1.0, 1.0),
        }
    )
    guard = prize_guard({0: PlaceStats(content=ROWS)}, plan, 0)
    assert guard.hops == {4: 5, 7: 1}
    rng = random.Random(3)
    assert {guard.level(rng, 4) for _ in range(40)} == {5, 6, 7}
    assert {guard.level(rng, 7) for _ in range(10)} == {3}


def test_a_level_without_statistics_still_draws_a_guard() -> None:
    guard = prize_guard({}, ContentPlan(), 1)
    assert guard.level(random.Random(1), 0) in EVERY_LEVEL


def test_the_same_seed_draws_the_same_guards() -> None:
    guard = prize_guard({0: PlaceStats(content=ROWS)}, ContentPlan(), 0)
    draws = [[guard.level(random.Random(s), 0) for s in range(20)] for _ in range(2)]
    assert draws[0] == draws[1]
