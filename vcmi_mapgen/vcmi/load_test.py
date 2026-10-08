import os
from pathlib import Path

from vcmi_mapgen.core.model import Footprint, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.road import Road
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.footprint import footprint_of
from vcmi_mapgen.vcmi.formats.vmap.document import PlayerSlot, VmapDocument, VmapObject
from vcmi_mapgen.vcmi.formats.vmap.writer import write
from vcmi_mapgen.vcmi.load import load_map, map_owners
from vcmi_mapgen.vcmi.tiles import TilerTables, tile_strings


def test_load_map_prefers_ontology_mask_over_file_mask(tmp_path: Path) -> None:
    """A known animation (a town) must get the ontology's canonical mask, not whatever
    happened to be written in the file -- this is the mask-correctness fix: a real .vmap's
    template.mask can't distinguish 'X' (blocked entrance) from 'A' (walk-on), so it is
    never trusted for an object the ontology has data for."""
    known_anim = "avctowx0"
    assert ON.has_animation(known_anim), "fixture assumes this animation is in the ontology"
    ontology_mask = ON.mask_of(known_anim)
    assert any("B" in row for row in ontology_mask), "fixture assumes a blocking footprint"

    doc = VmapDocument(
        name="fixture",
        width=5,
        height=5,
        two_level=False,
        terrain=[[["gr0_"] * 5] * 5],
        objects=[
            VmapObject(
                instance_name="t_1",
                type="town",
                subtype="castle",
                level=0,
                x=3,
                y=3,
                animation=known_anim,
                mask=["A"],  # deliberately WRONG/lossy on-disk mask (as if X had collapsed to A)
            )
        ],
    )
    m = load_map(write(doc, os.path.join(tmp_path, "fixture.vmap")))
    assert m.objs[0].footprint == footprint_of(ontology_mask)
    assert m.objs[0].purpose == Purpose.TOWN


def test_load_map_falls_back_to_file_mask_when_ontology_is_silent(tmp_path: Path) -> None:
    """Heroes' per-portrait animations aren't in objects.txt's ontology catalog at all --
    ON.mask_of would default to a conservative all-blocking ['B'], silently misclassifying
    every corpus hero as blocking. The file's own (unambiguous, no 'B' cell) mask must be
    used instead whenever the ontology has no data for the animation."""
    unknown_anim = "not_a_real_ontology_animation_xyz"
    assert not ON.has_animation(unknown_anim)

    doc = VmapDocument(
        name="fixture",
        width=5,
        height=5,
        two_level=False,
        terrain=[[["gr0_"] * 5] * 5],
        objects=[
            VmapObject(
                instance_name="h_1",
                type="hero",
                subtype="lordHaart",
                level=0,
                x=1,
                y=1,
                animation=unknown_anim,
                mask=["A"],
            )
        ],
    )
    m = load_map(write(doc, os.path.join(tmp_path, "fixture.vmap")))
    assert m.objs[0].footprint == Footprint.one(Role.VISIT)


def test_load_map_reads_back_each_road_and_its_type(tmp_path: Path) -> None:
    roads = {(1, 2): Road.DIRT, (2, 2): Road.GRAVEL, (3, 2): Road.COBBLESTONE}
    grid = [[Terrain.GRASS] * 5 for _ in range(5)]
    doc = VmapDocument(
        name="roads",
        width=5,
        height=5,
        two_level=False,
        terrain=[tile_strings(grid, TilerTables({}, {}, {}), roads)],
        objects=[],
    )
    m = load_map(write(doc, os.path.join(tmp_path, "roads.vmap")))
    assert m.roads[0] == roads
    assert m.terrain[0][2][2] == Terrain.GRASS


def test_map_owners_ranks_each_owner_among_the_sorted_colours(tmp_path: Path) -> None:
    def town(x: int, owner: str | None) -> VmapObject:
        return VmapObject(
            instance_name=f"t_{x}",
            type="town",
            subtype="castle",
            level=0,
            x=x,
            y=3,
            animation="avctowx0",
            mask=["A"],
            options={"owner": owner} if owner else None,
        )

    doc = VmapDocument(
        name="fixture",
        width=12,
        height=5,
        two_level=False,
        terrain=[[["gr0_"] * 12] * 5],
        objects=[town(4, "red"), town(8, "blue"), town(11, None)],
        players=[PlayerSlot(id="red"), PlayerSlot(id="blue")],
    )
    path = write(doc, os.path.join(tmp_path, "fixture.vmap"))
    assert map_owners(path) == {(8, 3, 0): 0, (4, 3, 0): 1}
