"""Reliability tests for steps.repair.step's nearby-guard dedup pass."""
from vcmi_mapgen.steps.repair.step import _dedup_nearby_guards


def _guard(x, y, lvl="randomMonsterLevel1", **extra):
    return {"x": x, "y": y, "l": 0, "purpose": "GUARD", "type": lvl,
            "subtype": "object", "mask": ["A"], **extra}


def _mine(x, y):
    return {"x": x, "y": y, "l": 0, "purpose": "MINE", "mask": ["A"]}


def _access(purpose, x, y):
    return {"x": x, "y": y, "l": 0, "purpose": purpose, "mask": ["A"]}


def test_a_loot_zone_access_object_guard_survives_a_nearby_seal_guard():
    """A guard gating a QUEST_GATE/TRANSPORT access object is just as load-bearing as a
    mine's guard, and both outrank a border-seal back-path guard (user-mandated
    placement order: loot-zone access / mines / pockets get their guard first; a border
    crossing is only ever guarded as a last resort, after those three have already
    claimed theirs). The access guard must survive a conflict with a seal guard, and the
    seal guard is the one dropped -- not "both survive," which was the old, now-wrong
    behavior when seal guards were unconditionally protected."""
    gate = _access("TRANSPORT", 14, 4)
    access_guard = _guard(13, 5, lvl="randomMonsterLevel7")   # Chebyshev 1 from the gate
    seal_guard = _guard(11, 6, lvl="randomMonsterLevel4", seal=True)  # Chebyshev 2 from access_guard
    objs = [gate, access_guard, seal_guard]

    deduped, ndrop = _dedup_nearby_guards(objs)

    assert ndrop == 1
    assert access_guard in deduped
    assert seal_guard not in deduped


def test_a_pocket_guard_survives_a_nearby_seal_guard():
    """Pockets rank above a border-seal guard too (third in the mandated order, but
    still above "no priority at all")."""
    pocket_guard = _guard(20, 20, lvl="randomMonsterLevel3", pocket_guard=True)
    seal_guard = _guard(21, 21, lvl="randomMonsterLevel6", seal=True)   # Chebyshev 1

    deduped, ndrop = _dedup_nearby_guards([pocket_guard, seal_guard])

    assert ndrop == 1
    assert pocket_guard in deduped
    assert seal_guard not in deduped


def test_a_mine_guard_survives_a_nearby_seal_guard():
    mine_guard = _guard(30, 30, lvl="randomMonsterLevel2")
    mine = _mine(30, 29)   # Chebyshev 1 from mine_guard, makes it tier-0
    seal_guard = _guard(31, 31, lvl="randomMonsterLevel7", seal=True)   # Chebyshev 1 from mine_guard

    deduped, ndrop = _dedup_nearby_guards([mine, mine_guard, seal_guard])

    assert ndrop == 1
    assert mine_guard in deduped
    assert seal_guard not in deduped


def test_two_nearby_seal_guards_keep_only_the_stronger():
    """Two lowest-tier guards conflicting with EACH OTHER still fall back to the
    stronger-monster tiebreak -- the tier system only changes cross-tier conflicts."""
    weak = _guard(40, 40, lvl="randomMonsterLevel1", seal=True)
    strong = _guard(41, 41, lvl="randomMonsterLevel7", seal=True)

    deduped, ndrop = _dedup_nearby_guards([weak, strong])

    assert ndrop == 1
    assert strong in deduped
    assert weak not in deduped


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
