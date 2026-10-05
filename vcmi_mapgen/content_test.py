"""A content setting that bans objects keeps them off a whole generated map, including the
rewards and quests the map's objects carry."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.conftest import corpus_tiler, find_install
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.renderers import VmapRenderer
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.content.enabled import EnabledSet
from vcmi_mapgen.vcmi.formats import vmap as VM

BANNED = frozenset(
    {"treasureChest", "witchHut", "oakTrees", "campfire", "speculum", "seaCaptainsHat"}
)


@pytest.mark.skipif(find_install() is None, reason="needs the VCMI config of a local install")
def test_a_banned_object_stays_off_the_map(priors: Priors, tmp_path: Path) -> None:
    config = StepConfig(1, 48)
    pipeline = Pipeline(VcmiCatalog(EnabledSet(banned=BANNED)), config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    state = pipeline.run()
    path = VmapRenderer(str(tmp_path), corpus_tiler()).render(state, "ban.vmap", name="ban")
    text = json.dumps([dataclasses.asdict(o) for o in VM.read(path).objects])
    assert not {name for name in BANNED if re.search(rf"\b{name}\b", text)}
