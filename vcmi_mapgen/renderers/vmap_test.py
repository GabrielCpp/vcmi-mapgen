"""Reliability tests for renderers.vmap (VmapRenderer: .vmap export + playability overlay)."""

import os
import zipfile
from pathlib import Path

import pytest

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.model import Identity, JsonValue, MapState, PlacedObject
from vcmi_mapgen.core.steps.gameplay import mines as PG
from vcmi_mapgen.core.steps.gameplay.step import place_open_zone
from vcmi_mapgen.kit import tiling as ZE
from vcmi_mapgen.renderers.vmap import VmapRenderer, parse_teams
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall


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


def _template_mask(vo: dict[str, JsonValue]) -> list[str]:
    return jv.str_list(jv.as_object(vo["template"]).get("mask"))


def _opts(o: PlacedObject) -> dict[str, JsonValue]:
    assert o.options is not None
    return o.options


def _vopts(vo: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return jv.as_object(vo["options"])


def _players(h: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {pid: pl for pid, pl in jv.as_object(h.get("players")).items() if isinstance(pl, dict)}


def test_parse_teams() -> None:
    assert parse_teams("ffa", 3) == [0, 1, 2]
    assert parse_teams("2v2", 4) == [0, 0, 1, 1]
    assert parse_teams("1v3", 4) == [0, 1, 1, 1]
    assert parse_teams("0,0,1,1", 4) == [0, 0, 1, 1]
    with pytest.raises(ValueError):
        _ = parse_teams("2v2", 3)


@needs_vcmi
def test_vmap_export_roundtrip(tmp_path: Path) -> None:
    """VmapRenderer writes an editor-shaped .vmap: reads back, visitables carry
    visitableFrom, and a playable slot is wired to the town."""
    grid = [[2] * 16 for _ in range(16)]
    cells = ZE.tile_terrain(grid, 16, 16)
    town = ON.gameplay_pool("grass", "TOWN")[0]
    objs = [_town(town, 8, 8)]
    state = MapState(size=max(len(cells), len(cells[0])), cells={0: cells}, objs=objs)
    p = VmapRenderer(out_dir=str(tmp_path), install=INSTALL).render(
        state, "test_pp_export.vmap", name="test"
    )
    z = zipfile.ZipFile(p)
    surf = jv.as_list(_load(z, "surface_terrain.json"))
    vobjs = _objects(p)
    header = jv.as_object(_load(z, "header.json"))
    assert len(surf) == 16 and len(vobjs) == 1
    assert jv.as_object(vobjs[0]["template"]).get("visitableFrom"), "town must carry visitableFrom"
    # VCMI's mask parser only knows ' 0VBHAT' — our internal 'X' (entrance cell) must be
    # exported as 'A' or the object is silently unvisitable in-game (found in playtest:
    # "ERROR Unrecognized char X in template mask", mines could not be flagged)
    for vo in vobjs:
        for row in _template_mask(vo):
            assert set(row) <= set(" 0VBHAT"), f"invalid VCMI mask row {row!r}"
    assert any("A" in row for row in _template_mask(vobjs[0])), (
        "the town's entrance cell must survive as a VCMI-visitable 'A'"
    )
    wired = [pl for pl in _players(header).values() if pl.get("mainTown")]
    assert wired, "a player slot must be wired to the town"


@needs_vcmi
def test_vmap_export_game_contracts(tmp_path: Path) -> None:
    """Round-2 playtest contracts (v5.2): mask orientation matches the art (the sawmill
    entrance is ONE tile left of the anchor, not mirrored), export masks are V-padded to
    the sprite tile extent (VCMI truncates sprites outside the mask), guards fight
    (character=hostile) and towns start with a fort."""
    # orientation: internal footprint un-mirrored, export mask == the mask VCMI's own RMG
    # writes for the same sawmill sprite (ground truth from Maps/RandomMaps). mask_of is
    # windowed identically to vmap_mask_of (same V-padding) so a guard's approach tile always
    # lands on the tile VCMI actually reads as visitable; only the X/A entrance glyph differs.
    assert ON.mask_of("avmsawg0") == ("VVVVV", "VVVBB", "VBBXB")
    assert ON.vmap_mask_of("avmsawg0") == ("VVVVV", "VVVBB", "VBBAB")
    assert ON.vmap_mask_of("avcranx0") == (
        "VVVVVV",
        "VVVVVV",
        "VVVVVV",
        "VVBBBV",
        "VBBBBB",
        "VBBABB",
    )
    if not os.path.exists(PG.STATS_PATH):
        pytest.skip("gameplay stats not mined")
    # a placed zone carries the game-time options on the right purposes
    ts = {(x, y) for x in range(30) for y in range(24)}
    objs: list[PlacedObject] = place_open_zone(ts, "grass", 3, player=True).gobjs
    town = next(o for o in objs if o.purpose == "TOWN")
    START_BUILDINGS: JsonValue = {
        "allOf": ["core:fort", "core:tavern", "core:dwellingLvl1", "core:dwellingLvl2"]
    }
    assert _opts(town)["buildings"] == START_BUILDINGS
    assert _opts(town)["possibleSpells"] == PG.CORE_SPELLS
    guards = [o for o in objs if o.purpose == "GUARD"]
    assert all(_opts(o)["character"] == "hostile" for o in guards)
    # random dwellings in a town zone are marked with the town's coordinates ...
    rdwell = [o for o in objs if (o.type or "").startswith("randomDwelling")]
    assert all(_opts(o)["sameAsTown"] == [town.x, town.y, 0] for o in rdwell)
    # ... and they survive the .vmap round trip, with sprite-extent masks
    grid = [[2] * 30 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 30, 24)
    state = MapState(size=max(len(cells), len(cells[0])), cells={0: cells}, objs=objs)
    p = VmapRenderer(out_dir=str(tmp_path), install=INSTALL).render(
        state, "test_pp_contracts.vmap", name="test"
    )
    vobjs = _objects(p)
    vtown = next(vo for vo in vobjs if vo.get("type") in ("town", "randomTown"))
    assert _vopts(vtown)["buildings"] == START_BUILDINGS
    assert _vopts(vtown)["possibleSpells"] == PG.CORE_SPELLS
    assert len(_template_mask(vtown)) == 6, "town mask must span the full sprite"
    # the coordinate marker resolved to the town's minted instanceName
    vdwell = [vo for vo in vobjs if jv.as_str(vo.get("type")).startswith("randomDwelling")]
    if rdwell:
        assert vdwell and all(_vopts(vo)["sameAsTown"] == vtown["instanceName"] for vo in vdwell)
    vguards = [
        vo
        for vo in vobjs
        if jv.as_str(vo.get("type")).startswith("randomMonster") or vo.get("type") == "monster"
    ]
    assert vguards and all(_vopts(vo)["character"] == "hostile" for vo in vguards)
    for vo in vobjs:
        for row in _template_mask(vo):
            assert set(row) <= set(" 0VBHAT"), f"invalid VCMI mask row {row!r}"
    saws = [vo for vo in vobjs if vo.get("subtype") == "sawmill"]
    assert saws and all(_template_mask(vo) == ["VVVVV", "VVVBB", "VBBAB"] for vo in saws)


@needs_vcmi
def test_playability_overlay(tmp_path: Path) -> None:
    """VmapRenderer's playability overlay: exactly N playable slots wired to their towns,
    team matrix set, victory = defeat all (standardWin)."""
    grid = [[2] * 24 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 24, 24)
    town = ON.gameplay_pool("grass", "TOWN")[0]
    towns = [_town(town, 8, 8), _town(town, 18, 18)]
    state = MapState(
        size=max(len(cells), len(cells[0])), cells={0: cells}, objs=towns, player_towns=towns
    )
    p = VmapRenderer(out_dir=str(tmp_path), install=INSTALL).render(
        state, "test_pp_play.vmap", name="test", teams_spec="ffa"
    )
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
    p = VmapRenderer(out_dir=str(tmp_path), install=INSTALL).render(
        state, "test_pp_play_2v2.vmap", name="test", teams_spec="2v2"
    )
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
    rnd = ON.identity_of(PG.RND_TOWN)
    grid = [[2] * 24 for _ in range(24)]
    cells = ZE.tile_terrain(grid, 24, 24)
    towns = [_town(rnd, 8, 8)]
    state = MapState(
        size=max(len(cells), len(cells[0])), cells={0: cells}, objs=towns, player_towns=towns
    )
    p = VmapRenderer(out_dir=str(tmp_path), install=INSTALL).render(
        state, "test_pp_play_random.vmap", name="test", teams_spec="ffa"
    )
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
