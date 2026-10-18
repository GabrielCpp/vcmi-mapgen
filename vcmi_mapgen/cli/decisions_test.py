"""Tests for the decisions record."""

import json
from pathlib import Path
from typing import cast

from vcmi_mapgen.cli.decisions import decisions_records, write_decisions
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


def _registry(catalog: Catalog) -> tuple[ProviderRegistry, MapState, str | None, str | None]:
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
    return ctx, map_state, dealt.type, fallback.type


def test_a_held_slot_shows_the_artifact_that_finally_stands_there(catalog: Catalog) -> None:
    """Defect caught: the record names the artifact the loot step would have placed, not the
    one the sets step dealt onto the held slot."""
    ctx, map_state, dealt, fallback = _registry(catalog)
    records = decisions_records(catalog, ctx, map_state)
    pocket = next(r for r in records if r["section"] == "pocket")
    shown = cast(dict[str, object], cast(dict[str, object], pocket["ward"])["object"])
    assert shown["type"] == dealt
    assert shown["type"] != fallback
    slot = next(r for r in records if r["section"] == "gameplay")
    assert cast(dict[str, object], slot["stood"])["tile"] == [4, 5]


def test_every_line_is_one_record_led_by_its_section_and_level(
    catalog: Catalog, tmp_path: Path
) -> None:
    """Defect caught: a record spans lines or hides its section, so a grep for a tile or a
    section returns fragments instead of whole decisions."""
    ctx, map_state, _, _ = _registry(catalog)
    lines = write_decisions(tmp_path, catalog, ctx, map_state).read_text().splitlines()
    records = [cast(dict[str, object], json.loads(line)) for line in lines]
    assert [list(r)[:2] for r in records] == [["section", "level"]] * len(records)
    assert {r["section"] for r in records} == {"loot_candidates", "quest", "pocket", "gameplay"}
    assert all("[4,5]" in line for line in lines if '"section":"pocket"' in line)


def test_a_run_stopped_early_still_writes_its_records(catalog: Catalog, tmp_path: Path) -> None:
    """Defect caught: a --stop-after run crashes on a missing result instead of writing the
    records it has."""
    assert decisions_records(catalog, ProviderRegistry(), MapState(size=4)) == []
    path = write_decisions(tmp_path, catalog, ProviderRegistry(), MapState(size=4))
    assert path.name == "decisions.jsonl" and path.read_text() == ""
