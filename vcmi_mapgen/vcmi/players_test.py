"""Tests for vcmi.players: player slots, teams and victory on the header."""

import zipfile
from pathlib import Path

import pytest

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.model import Identity, JsonValue, MapState, PlacedObject
from vcmi_mapgen.kit import tiling as ZE
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.roles import RANDOM_TOWN
from vcmi_mapgen.vcmi.export import build_document
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall
from vcmi_mapgen.vcmi.players import apply_playability, parse_teams


def _install() -> VcmiInstall | None:
    try:
        return load_settings().install()
    except InstallNotFoundError:
        return None


INSTALL = _install()
needs_vcmi = pytest.mark.skipif(
    INSTALL is None or not any((INSTALL.home / "Maps" / "RandomMaps").glob("*.vmap")),
    reason="VCMI template .vmap not available",
)


def _town(ident: Identity, x: int, y: int) -> PlacedObject:
    return PlacedObject.at(ident, (x, y), purpose="TOWN")


def _load(z: zipfile.ZipFile, name: str) -> JsonValue:
    return jv.loads(z.read(name).decode())


def _objects(p: str) -> list[dict[str, JsonValue]]:
    return [jv.as_object(o) for o in jv.as_list(_load(zipfile.ZipFile(p), "objects.json"))]


def _vopts(vo: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return jv.as_object(vo["options"])


def _players(h: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {pid: pl for pid, pl in jv.as_object(h.get("players")).items() if isinstance(pl, dict)}


def _write(state: MapState, path: Path, teams_spec: str) -> str:
    doc = build_document(state, "test", INSTALL)
    teams = parse_teams(teams_spec, len(state.player_towns))
    apply_playability(doc, state.player_towns, teams)
    return VM.write(doc, str(path))


def test_parse_teams() -> None:
    assert parse_teams("ffa", 3) == [0, 1, 2]
    assert parse_teams("2v2", 4) == [0, 0, 1, 1]
    assert parse_teams("1v3", 4) == [0, 1, 1, 1]
    assert parse_teams("0,0,1,1", 4) == [0, 0, 1, 1]
    with pytest.raises(ValueError):
        _ = parse_teams("2v2", 3)


@needs_vcmi
def test_playability_overlay(tmp_path: Path) -> None:
    """The playability overlay: exactly N playable slots wired to their towns,
    team matrix set, victory = defeat all (standardWin)."""
    grid = [[2] * 24 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 24, 24)
    town = ON.gameplay_pool("grass", "TOWN")[0]
    towns = [_town(town, 8, 8), _town(town, 18, 18)]
    state = MapState(
        size=max(len(cells), len(cells[0])), cells={0: cells}, objs=towns, player_towns=towns
    )
    p = _write(state, tmp_path / "test_pp_play.vmap", "ffa")
    h = jv.as_object(_load(zipfile.ZipFile(p), "header.json"))
    playable = {pid: pl for pid, pl in _players(h).items() if pl.get("canPlay") == "PlayerOrAI"}
    assert len(playable) == 2, "exactly N playable slots"
    wired = sorted(
        (
            jv.as_int(jv.as_object(pl["mainTown"]).get("x")),
            jv.as_int(jv.as_object(pl["mainTown"]).get("y")),
        )
        for pl in playable.values()
    )
    assert wired == [(6, 6), (16, 16)], "each player wired to its designated town (-2 offset)"
    assert sorted(jv.as_int(pl["team"]) for pl in playable.values()) == [0, 1]
    assert "teams" not in h, "no repeated team id (FFA/singletons) -> no top-level grouping"
    # these test towns are CONCRETE, so the lobby must be locked to the authored faction
    # (a randomTown start would instead clear allowedFactions — free lobby pick)
    for pl in playable.values():
        af = pl.get("allowedFactions")
        assert af == {"anyOf": [f"core:{towns[0].subtype}"]}, (
            f"concrete start town must restrict allowedFactions, got {af}"
        )
    for pid, pl in _players(h).items():
        if pid not in playable:
            assert pl.get("canPlay") == "false" and pl.get("mainTown") is None


@needs_vcmi
def test_playability_overlay_alliance_grouping(tmp_path: Path) -> None:
    """A real 2v2 alliance (repeated team ids) must populate the top-level
    header["teams"] grouping — this is what VCMI's map-select screen actually reads to
    show alliances; the per-player "team" int alone is not enough (bug reported
    2026-07-05: '2v2' teams weren't shown when the map was selected in VCMI)."""
    grid = [[2] * 24 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 24, 24)
    town = ON.gameplay_pool("grass", "TOWN")[0]

    towns = [_town(town, 8, 8), _town(town, 18, 18), _town(town, 8, 18), _town(town, 18, 8)]
    state = MapState(
        size=max(len(cells), len(cells[0])), cells={0: cells}, objs=towns, player_towns=towns
    )
    p = _write(state, tmp_path / "test_pp_play_2v2.vmap", "2v2")
    h = jv.as_object(_load(zipfile.ZipFile(p), "header.json"))
    assert sorted(sorted(jv.str_list(g)) for g in jv.as_list(h["teams"])) == [
        ["blue", "green"],
        ["orange", "red"],
    ]


@needs_vcmi
def test_playability_overlay_random_town_shows_random_in_lobby(tmp_path: Path) -> None:
    """A randomTown start must set randomFaction=true, or VCMI's PlayerInfo::defaultCastle()
    (isFactionRandom false + allowedFactions defaulting to ALL on an absent key) picks the
    first faction by id (Castle) instead of showing 'random' in the lobby — the bug reported
    2026-07-03: every player's town appeared fixed to Castle."""
    rnd = ON.identity_of(RANDOM_TOWN)
    grid = [[2] * 24 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 24, 24)
    towns = [_town(rnd, 8, 8)]
    state = MapState(
        size=max(len(cells), len(cells[0])), cells={0: cells}, objs=towns, player_towns=towns
    )
    p = _write(state, tmp_path / "test_pp_play_random.vmap", "ffa")
    h = jv.as_object(_load(zipfile.ZipFile(p), "header.json"))
    pl = next(pl for pl in _players(h).values() if pl.get("canPlay") == "PlayerOrAI")
    assert pl.get("randomFaction") is True, "randomTown start must set randomFaction=true"
    assert "allowedFactions" not in pl, "no faction restriction on a free random pick"
    # the town OBJECT still carries options.owner (mainTown alone is not enough)
    owners = [
        _vopts(o)["owner"]
        for o in _objects(p)
        if o.get("type") in ("town", "randomTown")
        and jv.as_object(o.get("options")).get("owner") is not None
    ]
    assert owners == ["blue"], "the single town must be owned by the sole (blue) player"
