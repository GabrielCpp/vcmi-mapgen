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


def test_draw_reward_is_seed_deterministic() -> None:
    for tier in (PANDORA_TIER, SEERHUT_TIER):
        assert draw_reward(random.Random(4), tier) == draw_reward(random.Random(4), tier)


def test_seer_hut_tier_pays_above_the_pandora_tier() -> None:
    assert min(SEERHUT_TIER.gold) > min(PANDORA_TIER.gold)
    assert max(SEERHUT_TIER.experience) > max(PANDORA_TIER.experience)
    assert SEERHUT_TIER.creatures[1] > PANDORA_TIER.creatures[1]


def test_payloads_share_one_rewardable_shape() -> None:
    pandora = pandora_reward(random.Random(1))
    quest = seerhut_quest(random.Random(1), "shieldOfTheDwarvenLords")
    assert quest.artifact == "shieldOfTheDwarvenLords"
    assert isinstance(pandora, Reward) and isinstance(quest.reward, Reward)
