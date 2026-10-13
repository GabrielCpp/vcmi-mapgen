"""Tests for labelling the roles of the grown places."""

import random

from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout
from vcmi_mapgen.core.steps.terrain_gen.roles import allowed_roles, label_roles

ALL = [r for r in PlaceRole if r != PlaceRole.HOME]


def test_a_pocket_needs_one_neighbour_and_a_pass_another_territory() -> None:
    assert PlaceRole.POCKET in allowed_roles(ALL, 1, False)
    assert PlaceRole.POCKET not in allowed_roles(ALL, 2, True)
    assert PlaceRole.PASS in allowed_roles(ALL, 2, True)
    assert PlaceRole.PASS not in allowed_roles(ALL, 1, False)
    assert allowed_roles([PlaceRole.POCKET], 3, False) == [PlaceRole.MIDDLE]


def test_the_roles_keep_the_homes_and_the_rules(priors: Priors) -> None:
    label = [[min(x // 6, 5) for x in range(36)] for _ in range(36)]
    layout = Layout(label, tuple((p * 6 + 3, 18) for p in range(6)), 6)
    territory = [0, 0, 2, 2, 1, 1]
    for seed in range(6):
        roles = label_roles(layout, {0, 5}, territory, priors.places[0], random.Random(seed))
        assert roles[0] == roles[5] == PlaceRole.HOME
        assert PlaceRole.HOME not in roles[1:5]
        assert PlaceRole.POCKET not in roles[1:5]
        assert roles[2] != PlaceRole.PASS
