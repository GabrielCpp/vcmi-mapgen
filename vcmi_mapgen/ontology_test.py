"""Reliability tests for ontology.py's spell/artifact/monster level-classification
accessors (SPELL_LEVELS/ARTIFACT_TIERS/MONSTER_LEVELS, hand-extracted from H3's own
SPTRAITS.TXT/ARTRAITS.TXT and VCMI's config/creatures/*.json -- see ontology.py's
module-level comment for how)."""
from vcmi_mapgen import ontology as ON


def test_spell_levels_partition_1_through_5_only():
    """Every classified spell is level 1-5 -- creature-only abilities (Stone Gaze,
    Paralyze, ...) must never leak in (they'd fail this, being absent from
    SPELL_LEVELS entirely, but assert the invariant on whatever IS present)."""
    assert ON.SPELL_LEVELS, "fixture assumption broke: no spells loaded"
    assert all(1 <= lvl <= 5 for lvl in ON.SPELL_LEVELS.values())
    assert ON.spell_level("stoneGaze") is None, "a creature ability, not a hero spell"
    assert ON.spell_level("paralyze") is None, "a creature ability, not a hero spell"


def test_spells_by_level_matches_known_h3_rosters():
    """Spot-check against verified SPTRAITS.TXT data (not memory) -- these are exactly
    the well-known level 4/5 mage-guild spells."""
    assert ON.spell_level("townPortal") == 4
    assert ON.spell_level("waterWalk") == 4
    assert ON.spell_level("fly") == 5
    assert ON.spell_level("dimensionDoor") == 5
    assert "townPortal" in ON.spells_by_level(4)
    assert "fly" in ON.spells_by_level(5)
    assert "magicArrow" in ON.spells_by_level(1)


def test_spells_by_level_returns_sorted_unique_list():
    for level in (1, 2, 3, 4, 5):
        names = ON.spells_by_level(level)
        assert names == sorted(set(names))


def test_artifact_tiers_are_the_four_rarity_names_only():
    assert ON.ARTIFACT_TIERS, "fixture assumption broke: no artifacts loaded"
    assert set(ON.ARTIFACT_TIERS.values()) == {"treasure", "minor", "major", "relic"}


def test_artifact_tier_excludes_non_random_artifacts():
    """Spell Book, Spell Scroll, the Grail and war machines are not part of the
    randomly-obtainable tiered pool."""
    for name in ("spellBook", "spellScroll", "grail", "catapult", "ballista", "ammoCart"):
        assert ON.artifact_tier(name) is None, f"{name} should not carry a rarity tier"


def test_artifact_tier_matches_known_h3_examples():
    assert ON.artifact_tier("armageddonsBlade") == "relic"
    assert ON.artifact_tier("titansGladius") == "relic"


def test_monster_levels_cover_the_classic_1_to_7_town_tiers():
    assert ON.MONSTER_LEVELS, "fixture assumption broke: no creatures loaded"
    for level in range(1, 8):
        names = ON.monsters_by_level(level)
        assert names, f"expected at least one creature at level {level}"


def test_monster_level_matches_known_h3_examples():
    assert ON.monster_level("pikeman") == 1
    assert ON.monster_level("archangel") == 7
    assert ON.monster_level("griffin") == 3


def test_unknown_identifiers_return_none_not_raise():
    assert ON.spell_level("notARealSpell") is None
    assert ON.artifact_tier("notARealArtifact") is None
    assert ON.monster_level("notARealCreature") is None
