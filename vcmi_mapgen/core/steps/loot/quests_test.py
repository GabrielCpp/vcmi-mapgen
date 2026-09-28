"""Tests for the seer hut quests."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Quest, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.loot.quests import SeerHutContext, place_seer_hut_quests


def _record(zid: int, x0: int) -> ZoneRecord:
    ts = {(x, y) for x in range(x0, x0 + 12) for y in range(12)}
    return ZoneRecord(
        zid=zid,
        terrain="grass",
        ts=frozenset(ts),
        open_set=frozenset(ts),
        passable=frozenset(ts),
        reach=frozenset(ts),
    )


def test_seer_hut_asks_for_the_artifact_placed_for_it(catalog: Catalog, priors: Priors) -> None:
    records = [_record(0, 0), _record(1, 12)]
    pocket: set[Tile] = {t for zr in records for t in zr.ts if t[1] >= 9}
    used: set[str] = set()
    objs, n = place_seer_hut_quests(
        catalog,
        records,
        seed=5,
        bounds=(24, 12),
        context=SeerHutContext(priors.gameplay[0], pocket_tiles=pocket, used_artifacts=used),
    )
    assert n == 1
    arts = [o for o in objs if o.purpose == Purpose.REWARD_PICKUP]
    huts = [o for o in objs if o.purpose == Purpose.QUEST_GATE]
    assert len(arts) == 1 and len(huts) == 1
    art = catalog.identity_of(arts[0].kind).subtype
    assert used == {art}
    quest = huts[0].payload
    assert isinstance(quest, Quest) and quest.artifact == art
