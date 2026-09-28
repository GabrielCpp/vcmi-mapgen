"""Tests for vcmi.export: a MapState becomes an editor-shaped .vmap."""

import zipfile
from pathlib import Path

import pytest

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.model import Identity, JsonValue, MapState, PlacedObject
from vcmi_mapgen.kit import tiling as ZE
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.export import build_document
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats import vmap as VM
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


def _players(h: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {pid: pl for pid, pl in jv.as_object(h.get("players")).items() if isinstance(pl, dict)}


def _write(state: MapState, path: Path) -> str:
    return VM.write(build_document(state, "test", INSTALL), str(path))


@needs_vcmi
def test_vmap_export_roundtrip(tmp_path: Path) -> None:
    """build_document writes an editor-shaped .vmap: reads back, visitables carry
    visitableFrom, and a playable slot is wired to the town."""
    grid = [[2] * 16 for _ in range(16)]
    cells = ZE.tile_terrain(grid, 16, 16)
    town = ON.gameplay_pool("grass", "TOWN")[0]
    objs = [_town(town, 8, 8)]
    state = MapState(size=max(len(cells), len(cells[0])), cells={0: cells}, objs=objs)
    p = _write(state, tmp_path / "test_pp_export.vmap")
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
