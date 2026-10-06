"""Tests for the one reward builder and the payloads built on it."""

import random

from vcmi_mapgen.core.model import Reward
from vcmi_mapgen.core.placement.rewards import (
    PANDORA_TIER,
    SEERHUT_TIER,
    draw_reward,
    pandora_reward,
    seerhut_quest,
)
from vcmi_mapgen.core.priors.effort import RewardTier

CREATURES = {1: ["peasant"], 6: ["angel"], 7: ["archangel"]}
STACKS = RewardTier((0, 0, 1), (1000,), (5000,), (2, 4), (6, 7))


def test_draw_reward_is_seed_deterministic() -> None:
    for tier in (PANDORA_TIER, SEERHUT_TIER):
        a = draw_reward(random.Random(4), tier, CREATURES)
        assert a == draw_reward(random.Random(4), tier, CREATURES)


def test_a_stack_comes_from_one_of_the_tier_levels() -> None:
    rng = random.Random(2)
    names = {draw_reward(rng, STACKS, CREATURES).creatures[0][0] for _ in range(40)}
    assert names == {"angel", "archangel"}


def test_a_stack_with_no_creature_of_its_level_pays_experience() -> None:
    reward = draw_reward(random.Random(2), STACKS, {1: ["peasant"]})
    assert reward == Reward(experience=5000)


def test_seer_hut_tier_pays_above_the_pandora_tier() -> None:
    assert min(SEERHUT_TIER.gold) > min(PANDORA_TIER.gold)
    assert max(SEERHUT_TIER.experience) > max(PANDORA_TIER.experience)
    assert SEERHUT_TIER.creatures[1] > PANDORA_TIER.creatures[1]


def test_seer_hut_stack_is_worth_its_gold() -> None:
    rng = random.Random(3)
    creatures = {1: ["peasant"], 4: ["swordsman"], 5: ["monk"]}
    stacks = [
        r.creatures[0][0]
        for r in (draw_reward(rng, SEERHUT_TIER, creatures) for _ in range(200))
        if r.creatures
    ]
    assert stacks and set(stacks) == {"swordsman", "monk"}


def test_pandora_stack_is_worth_its_gold() -> None:
    rng = random.Random(3)
    creatures = {1: ["peasant"], 2: ["archer"], 3: ["griffin"]}
    stacks = [
        r.creatures[0][0]
        for r in (draw_reward(rng, PANDORA_TIER, creatures) for _ in range(200))
        if r.creatures
    ]
    assert stacks and set(stacks) == {"archer", "griffin"}


def test_payloads_share_one_rewardable_shape() -> None:
    pandora = pandora_reward(random.Random(1), CREATURES)
    quest = seerhut_quest(random.Random(1), "shieldOfTheDwarvenLords", CREATURES)
    assert quest.artifact == "shieldOfTheDwarvenLords"
    assert isinstance(pandora, Reward) and isinstance(quest.reward, Reward)
