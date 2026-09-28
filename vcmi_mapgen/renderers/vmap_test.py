"""End-to-end test of VmapRenderer: a placed zone written to .vmap keeps its game contracts."""

import zipfile
from pathlib import Path

import pytest

from vcmi_mapgen.conftest import (
    OpenZone,
    OpenZonePlacer,
    corpus_tiler,
    find_install,
    gameplay_mined,
)
from vcmi_mapgen.core.model import JsonValue, MapState, PlacedObject
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.renderers.vmap import VmapRenderer
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.options import CORE_SPELLS, options_of

INSTALL = find_install()
needs_vcmi = pytest.mark.skipif(
    INSTALL is None or not any((INSTALL.home / "Maps" / "RandomMaps").glob("*.vmap")),
    reason="VCMI template .vmap not available",
)


def _load(z: zipfile.ZipFile, name: str) -> JsonValue:
    return jv.loads(z.read(name).decode())


def _objects(p: str) -> list[dict[str, JsonValue]]:
    return [jv.as_object(o) for o in jv.as_list(_load(zipfile.ZipFile(p), "objects.json"))]


def _template_mask(vo: dict[str, JsonValue]) -> list[str]:
    return jv.str_list(jv.as_object(vo["template"]).get("mask"))


def _opts(o: PlacedObject) -> dict[str, JsonValue]:
    opts = options_of(o.payload)
    assert opts is not None
    return opts


def _vopts(vo: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return jv.as_object(vo["options"])


@needs_vcmi
def test_vmap_export_game_contracts(open_zone: OpenZonePlacer, tmp_path: Path) -> None:
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
    if not gameplay_mined():
        pytest.skip("gameplay stats not mined")
    # a placed zone carries the game-time options on the right purposes
    ts = {(x, y) for x in range(30) for y in range(24)}
    objs: list[PlacedObject] = list(open_zone(OpenZone(ts, "grass", player=True), 3).objs)
    town = next(o for o in objs if o.purpose == "TOWN")
    START_BUILDINGS: JsonValue = {
        "allOf": ["core:fort", "core:tavern", "core:dwellingLvl1", "core:dwellingLvl2"]
    }
    assert _opts(town)["buildings"] == START_BUILDINGS
    assert _opts(town)["possibleSpells"] == CORE_SPELLS
    guards = [o for o in objs if o.purpose == "GUARD"]
    assert all(_opts(o)["character"] == "hostile" for o in guards)
    # random dwellings in a town zone are marked with the town's coordinates ...
    rdwell = [o for o in objs if (ON.identity_of(o.kind).type or "").startswith("randomDwelling")]
    assert all(_opts(o)["sameAsTown"] == [town.x, town.y, 0] for o in rdwell)
    # ... and they survive the .vmap round trip, with sprite-extent masks
    grid = [[2] * 30 for _ in range(24)]
    terrain = [[Terrain(t) for t in row] for row in grid]
    state = MapState(size=max(len(terrain), len(terrain[0])), terrain={0: terrain}, objs=objs)
    p = VmapRenderer(str(tmp_path), corpus_tiler(), INSTALL).render(
        state, "test_pp_contracts.vmap", name="test"
    )
    vobjs = _objects(p)
    vtown = next(vo for vo in vobjs if vo.get("type") in ("town", "randomTown"))
    assert _vopts(vtown)["buildings"] == START_BUILDINGS
    assert _vopts(vtown)["possibleSpells"] == CORE_SPELLS
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
