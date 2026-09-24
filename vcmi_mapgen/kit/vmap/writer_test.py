import os
import zipfile
from pathlib import Path

from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit.vmap.document import PlayerSlot, VmapDocument
from vcmi_mapgen.kit.vmap.writer import write
from vcmi_mapgen.models import JsonValue


def _minimal_doc(
    *,
    extra: dict[str, JsonValue] | None = None,
    teams: list[list[str]] | None = None,
    players: list[PlayerSlot] | None = None,
    two_level: bool = False,
    terrain: list[list[list[str]]] | None = None,
    width: int = 1,
    height: int = 1,
) -> VmapDocument:
    return VmapDocument(
        name="m",
        width=width,
        height=height,
        two_level=two_level,
        terrain=terrain if terrain is not None else [[["gr0_"]]],
        players=players if players is not None else [],
        teams=teams,
        extra=extra if extra is not None else {},
    )


def _header(path: str) -> dict[str, JsonValue]:
    with zipfile.ZipFile(path) as z:
        return jv.as_object(jv.loads(z.read("header.json").decode()))


def test_teams_key_omitted_when_none_even_if_extra_had_it(tmp_path: Path) -> None:
    """Real VCMI RMG maps omit `teams` entirely for FFA (VmapRenderer's own convention);
    a document built fresh (teams=None) must not resurrect a stale extra['teams']."""
    doc = _minimal_doc(extra={"teams": [["red"]]}, teams=None)
    h = _header(write(doc, os.path.join(tmp_path, "m.vmap")))
    assert "teams" not in h


def test_player_slot_extra_keys_survive_alongside_modeled_ones(tmp_path: Path) -> None:
    doc = _minimal_doc(
        players=[
            PlayerSlot(
                id="red",
                can_play="PlayerOrAI",
                team=1,
                extra={"aiTactic": "random", "posOfMainTown": None},
            ),
        ]
    )
    h = _header(write(doc, os.path.join(tmp_path, "m.vmap")))
    red = jv.as_object(jv.as_object(h["players"])["red"])
    assert red["canPlay"] == "PlayerOrAI"
    assert red["team"] == 1
    assert red["aiTactic"] == "random"


def test_unset_optional_player_fields_are_not_written(tmp_path: Path) -> None:
    doc = _minimal_doc(players=[PlayerSlot(id="blue", can_play="false")])
    h = _header(write(doc, os.path.join(tmp_path, "m.vmap")))
    blue = jv.as_object(jv.as_object(h["players"])["blue"])
    assert "team" not in blue
    assert "allowedFactions" not in blue
    assert "randomFaction" not in blue
    assert blue["mainTown"] is None


def test_two_level_writes_underground_terrain(tmp_path: Path) -> None:
    doc = _minimal_doc(
        two_level=True, terrain=[[["gr0_", "gr0_"]], [["rc0_", "rc0_"]]], width=2, height=1
    )
    path = write(doc, os.path.join(tmp_path, "m.vmap"))
    with zipfile.ZipFile(path) as z:
        assert "underground_terrain.json" in z.namelist()
    h = _header(path)
    assert jv.as_object(jv.as_object(h["mapLevels"])["underground"])["width"] == 2
