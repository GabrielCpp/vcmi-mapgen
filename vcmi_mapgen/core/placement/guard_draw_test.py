import random
from collections import Counter

from vcmi_mapgen.core.placement.guard_draw import GuardDraw
from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves, FamilyFit

CURVES = FamilyCurves(
    100,
    {
        "BANK": FamilyFit(CountCurve(0.0, 1.0, 0.0), 0.0, (0.75, 0.0, 0.25)),
        "DWELLING:7": FamilyFit(
            CountCurve(0.0, 1.0, 0.0), 0.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        ),
    },
)


def test_draws_follow_the_family_record() -> None:
    draw = GuardDraw(CURVES, 7)
    rng = random.Random(1)
    seen = Counter(draw.draw(rng, "BANK") for _ in range(4000))
    assert set(seen) == {0, 2}
    assert 0.7 < seen[0] / 4000 < 0.8


def test_a_family_with_no_record_stands_unguarded() -> None:
    assert GuardDraw(CURVES, 7).draw(random.Random(1), "MANA") == 0


def test_no_draw_goes_past_the_top_level() -> None:
    assert GuardDraw(CURVES, 5).draw(random.Random(1), "DWELLING:7") == 5


def test_the_same_seed_draws_the_same_guards() -> None:
    draw = GuardDraw(CURVES, 7)
    a, b = random.Random(9), random.Random(9)
    assert [draw.draw(a, "BANK") for _ in range(20)] == [draw.draw(b, "BANK") for _ in range(20)]
