"""Tests for cli.generate: overlay selection, the map's folder, its run record and its
planned topology."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from vcmi_mapgen.cli.generate import (
    DEFAULT_OVERLAYS,
    INSTALL_FOLDER,
    GenerateOptions,
    file_stem,
    fresh_folder,
    install_map,
    map_folder,
    parse_overlays,
    write_run,
    write_topology,
)
from vcmi_mapgen.core.model import Footprint, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.steps.doors.result import DoorGuard, DoorGuards, Shortfall, ShortPair
from vcmi_mapgen.core.steps.terrain_gen.result import (
    LevelPlaces,
    PlaceMap,
    PlannedDoor,
    TerritoryPlan,
)
from vcmi_mapgen.renderers.overlays import ZoneOverlay
from vcmi_mapgen.vcmi.content.enabled import ContentSetting
from vcmi_mapgen.vcmi.install import VcmiInstall

OPTS = GenerateOptions(
    seed=3,
    size=72,
    players=2,
    teams="",
    water_mode="topology",
    subterrain=False,
    overlays="none",
    renderers="png,vmap",
    stop_after=None,
    vegetation="field",
)


def test_zone_label_composites_last_regardless_of_requested_order() -> None:
    """PngRenderer.render composites overlays IN LIST ORDER (each later one painted
    over the earlier ones) -- so a zone-id label must be the LAST entry whenever
    "zone" is requested, or a later overlay (blocking/guard/pocket) buries it. This
    held even when "zone" was the first name in the spec, which is the reported bug:
    the default overlay order is "zone,blocking,guard,pocket"."""
    overlays = parse_overlays("zone,blocking,pocket", {}, {})
    assert isinstance(overlays[-1], ZoneOverlay)
    assert overlays[-1].labels is True
    assert overlays[-1].fill is False, "the trailing zone pass must be label-only"
    # the in-position "zone" entry must be fill-only, so the label isn't drawn twice
    zone_entries = [o for o in overlays if isinstance(o, ZoneOverlay)]
    assert len(zone_entries) == 2
    assert zone_entries[0].fill is True and zone_entries[0].labels is False


def test_zone_not_requested_no_trailing_label_pass() -> None:
    overlays = parse_overlays("blocking,pocket", {}, {})
    assert not any(isinstance(o, ZoneOverlay) for o in overlays)


def test_passage_overlay_not_in_default_selection() -> None:
    """The blue walkable-seam overlay must not render by default."""
    assert "passage" not in DEFAULT_OVERLAYS.split(",")


def test_file_stem_keeps_a_plain_title() -> None:
    assert file_stem("Twin Lakes") == "Twin Lakes"


def test_file_stem_replaces_the_characters_a_file_system_refuses() -> None:
    assert file_stem('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_install_map_copies_into_the_pp_gen_folder(tmp_path: Path) -> None:
    vmap = tmp_path / "out" / "Twin Lakes.vmap"
    vmap.parent.mkdir()
    _ = vmap.write_bytes(b"map")
    install = VcmiInstall(tmp_path / "vcmi", tmp_path / "vcmi" / "Data", ())
    installed = install_map(str(vmap), install)
    assert installed == tmp_path / "vcmi" / "Maps" / INSTALL_FOLDER / "Twin Lakes.vmap"
    assert installed.read_bytes() == b"map"


def test_map_folder_names_the_seed_and_the_size() -> None:
    assert map_folder(OPTS) == "ppmap_s3_72"


def test_map_folder_tags_a_sampler_other_than_the_default() -> None:
    assert map_folder(replace(OPTS, vegetation="gibbs")) == "ppmap_s3_72_gibbs"


def test_map_folder_takes_the_map_name() -> None:
    assert map_folder(replace(OPTS, name="Twin: Lakes")) == "Twin_ Lakes"


def test_fresh_folder_empties_what_an_earlier_run_left(tmp_path: Path) -> None:
    old = tmp_path / "ppmap_s3_72" / "nested" / "stale.png"
    old.parent.mkdir(parents=True)
    _ = old.write_bytes(b"old")
    folder = fresh_folder(tmp_path, "ppmap_s3_72")
    assert folder == tmp_path / "ppmap_s3_72"
    assert list(folder.iterdir()) == []


def test_fresh_folder_refuses_a_name_outside_the_out_folder(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _ = fresh_folder(tmp_path / "out", "../elsewhere")


def test_run_json_records_every_flag(tmp_path: Path) -> None:
    opts = replace(OPTS, content=ContentSetting(frozenset({"hota"}), frozenset({"angel"})))
    record = cast(dict[str, object], json.loads(write_run(tmp_path, opts).read_text()))
    assert record["seed"] == 3
    assert record["size"] == 72
    assert record["content"] == {"banned": ["angel"], "mods": ["hota"]}
    assert set(record) == set(GenerateOptions.__dataclass_fields__)


def test_topology_json_holds_the_early_graph_the_territories_the_doors_and_the_rivals(
    tmp_path: Path,
) -> None:
    door = PlannedDoor((0, 1), (0, 1), (2, None), ((3, 4), (4, 4)))
    plan = TerritoryPlan({0: 0, 1: 1}, (2, None), (door,))
    places = PlaceMap({0: LevelPlaces(((0, 1),), {}, frozenset({(0, 1)}), territories=plan)})
    obj = PlacedObject(4, 4, 0, Purpose.GUARD, "", Footprint.one(Role.BLOCKING))
    guards = DoorGuards(
        (DoorGuard(0, (0, 1), (4, 4), 5, obj, raised=2),),
        (ShortPair((0, 1), 5, Shortfall.SEA),),
    )
    record = cast(
        dict[str, object], json.loads(write_topology(tmp_path, places, guards).read_text())
    )
    assert record == {
        "levels": {
            "0": {
                "early_graph": [[0, 1]],
                "territories": {"0": 0, "1": 1},
                "owners": [2, None],
                "doors": [
                    {
                        "zones": [0, 1],
                        "territories": [0, 1],
                        "owners": [2, None],
                        "tiles": [[3, 4], [4, 4]],
                        "guard": {"tile": [4, 4], "level": 5, "raised": 2},
                    }
                ],
            }
        },
        "rivals": [{"players": [0, 1], "days": 5, "reason": "sea"}],
    }
