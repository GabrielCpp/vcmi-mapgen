"""Reliability tests for steps.repair.step's nearby-guard dedup pass."""
from vcmi_mapgen.steps.repair.step import _dedup_nearby_guards


def _guard(x, y, lvl="randomMonsterLevel1", **extra):
    return {"x": x, "y": y, "l": 0, "purpose": "GUARD", "type": lvl,
            "subtype": "object", "mask": ["A"], **extra}


def _mine(x, y):
    return {"x": x, "y": y, "l": 0, "purpose": "MINE", "mask": ["A"]}


def _access(purpose, x, y):
    return {"x": x, "y": y, "l": 0, "purpose": purpose, "mask": ["A"]}


def test_a_loot_zone_access_object_guard_survives_a_nearby_protected_guard():
    """A guard gating a QUEST_GATE/TRANSPORT access object is just as load-bearing
    as a mine's guard: it must never be dropped just because an unrelated
    protected guard (e.g. a border-seal 'seal' guard) lands within Chebyshev 2."""
    gate = _access("TRANSPORT", 14, 4)
    access_guard = _guard(13, 5, lvl="randomMonsterLevel7")   # Chebyshev 1 from the gate
    seal_guard = _guard(11, 6, lvl="randomMonsterLevel4", seal=True)  # Chebyshev 2 from access_guard
    objs = [gate, access_guard, seal_guard]

    deduped, ndrop = _dedup_nearby_guards(objs)

    assert ndrop == 0, "both the access-object guard and the seal guard are protected"
    assert access_guard in deduped
    assert seal_guard in deduped


def test_two_unprotected_nearby_guards_keep_only_the_stronger():
    weak = _guard(10, 10, lvl="randomMonsterLevel1")
    strong = _guard(11, 11, lvl="randomMonsterLevel7")
    deduped, ndrop = _dedup_nearby_guards([weak, strong])

    assert ndrop == 1
    assert strong in deduped
    assert weak not in deduped


def test_a_mine_guard_is_protected_from_an_unprotected_neighbor():
    mine = _mine(20, 20)
    mine_guard = _guard(20, 19, lvl="randomMonsterLevel1")   # Chebyshev 1 from the mine
    other = _guard(22, 19, lvl="randomMonsterLevel7")        # Chebyshev 2 from mine_guard,
    # but Chebyshev 2 from the mine itself -- NOT protected by mine-adjacency

    deduped, ndrop = _dedup_nearby_guards([mine, mine_guard, other])

    assert ndrop == 1
    assert mine_guard in deduped
    assert other not in deduped
