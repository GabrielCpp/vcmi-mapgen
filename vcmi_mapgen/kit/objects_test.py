import os

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.vmap.document import VmapDocument, VmapObject
from vcmi_mapgen.kit.vmap.writer import write


def test_load_faithful_prefers_ontology_mask_over_file_mask(tmp_path, monkeypatch):
    """A known animation (a town) must get the ontology's canonical mask, not whatever
    happened to be written in the file -- this is the mask-correctness fix: a real .vmap's
    template.mask can't distinguish 'X' (blocked entrance) from 'A' (walk-on), so it is
    never trusted for an object the ontology has data for."""
    known_anim = "avctowx0"
    assert ON.has_animation(known_anim), "fixture assumes this animation is in the ontology"
    ontology_mask = ON.mask_of(known_anim)
    assert any("B" in row for row in ontology_mask), "fixture assumes a blocking footprint"

    doc = VmapDocument(
        name="fixture", width=5, height=5, two_level=False,
        terrain=[[["gr0_"] * 5] * 5],
        objects=[VmapObject(
            instance_name="t_1", type="town", subtype="castle", l=0, x=3, y=3,
            animation=known_anim,
            mask=["A"],  # deliberately WRONG/lossy on-disk mask (as if X had collapsed to A)
        )],
    )
    path = write(doc, os.path.join(tmp_path, "fixture.vmap"))
    monkeypatch.setattr(OR, "faithful_path", lambda name: path)

    fm = OR.load_faithful("fixture")
    assert fm["objects"][0]["mask"] == ontology_mask


def test_load_faithful_falls_back_to_file_mask_when_ontology_is_silent(tmp_path, monkeypatch):
    """Heroes' per-portrait animations aren't in objects.txt's ontology catalog at all --
    ON.mask_of would default to a conservative all-blocking ['B'], silently misclassifying
    every corpus hero as blocking. The file's own (unambiguous, no 'B' cell) mask must be
    used instead whenever the ontology has no data for the animation."""
    unknown_anim = "not_a_real_ontology_animation_xyz"
    assert not ON.has_animation(unknown_anim)

    doc = VmapDocument(
        name="fixture", width=5, height=5, two_level=False,
        terrain=[[["gr0_"] * 5] * 5],
        objects=[VmapObject(
            instance_name="h_1", type="hero", subtype="lordHaart", l=0, x=1, y=1,
            animation=unknown_anim, mask=["A"],
        )],
    )
    path = write(doc, os.path.join(tmp_path, "fixture.vmap"))
    monkeypatch.setattr(OR, "faithful_path", lambda name: path)

    fm = OR.load_faithful("fixture")
    assert fm["objects"][0]["mask"] == ["A"]
    assert not OR.is_blocking(fm["objects"][0]["mask"])


def test_purpose_of_matches_type_to_purpose():
    assert OR.purpose_of({"type": "town"}) == OR.type_to_purpose("town") == "TOWN"
    assert OR.purpose_of({"type": None}) == "UNKNOWN"
