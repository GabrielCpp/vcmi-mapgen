"""Tests for the decisions record."""

from typing import cast

from vcmi_mapgen.cli.decisions import decisions_record
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, SlotRanking, Stood
from vcmi_mapgen.core.steps.loot.result import (
    LootResult,
    PocketDecision,
    PocketOutcome,
    QuestDecision,
)
from vcmi_mapgen.core.steps.vegetation.result import LootZones


def test_a_held_slot_shows_the_artifact_that_finally_stands_there(catalog: Catalog) -> None:
    """Defect caught: the record names the artifact the loot step would have placed, not the
    one the sets step dealt onto the held slot."""
    fallback = catalog.random_artifact("treasure")
    dealt = catalog.random_artifact("relic")
    obj = PlacedObject.at(dealt, (4, 5), purpose=Purpose.REWARD_PICKUP)
    map_state = MapState(size=8, objs=[obj])
    held = HeldPrize(0, (4, 5), "grass", fallback)
    pocket = PocketDecision(
        level=0,
        zone=1,
        planned=True,
        kind="deep",
        tiles=((4, 5),),
        mouth=((4, 4),),
        outcome=PocketOutcome.UNGUARDED,
        ward=held.tile,
        ward_tier="relic",
        ward_held=True,
    )
    quest = QuestDecision(0, (4, 5), 1, (4, 5), 2, "x")
    stood = Stood(0, 4, 5, "F", 0, "snug", False, 0, True, (4, 5), 0, 0)
    ranking = SlotRanking(0, "F", None, None, None, 0, (), (), (), 0, stood)
    ctx = ProviderRegistry()
    ctx.provide(LootResult(held=(held,), quests=(quest,), decisions=(pocket,)))
    ctx.provide(LootZones(candidates={0: frozenset({1})}))
    ctx.provide(GameplayResult({}, {}, {}, ranking=(ranking,)))
    record = decisions_record(catalog, ctx, map_state)
    assert set(record) == {"loot_zones", "treasure", "quests", "pockets", "gameplay"}
    ward = cast(dict[str, object], cast(list[dict[str, object]], record["pockets"])[0]["ward"])
    shown = cast(dict[str, object], ward["object"])
    assert shown["type"] == dealt.type
    assert shown["type"] != fallback.type
    gameplay = cast(list[dict[str, object]], record["gameplay"])
    assert cast(dict[str, object], gameplay[0]["stood"])["tile"] == [4, 5]


def test_a_run_stopped_early_still_has_all_five_sections(catalog: Catalog) -> None:
    """Defect caught: a --stop-after run crashes on a missing result instead of writing the
    sections it has."""
    record = decisions_record(catalog, ProviderRegistry(), MapState(size=4))
    assert set(record) == {"loot_zones", "treasure", "quests", "pockets", "gameplay"}
    assert record["pockets"] == [] and record["gameplay"] == []
