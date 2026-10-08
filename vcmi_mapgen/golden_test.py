"""Golden oracle: two generated maps hash to the values recorded in data/golden.json.

`make golden` runs it. `make golden-update` re-records the hashes, which only a
behaviour change may do."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.conftest import SETTINGS, corpus_tiler, find_install
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.renderers import VmapRenderer
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats import vmap as VM

GOLDEN = SETTINGS.root / "data" / "golden.json"
MAPS = (
    ("s1_48", StepConfig(1, 48)),
    ("s3_72_sub", StepConfig(3, 72, subterrain=True)),
)


INSTALL = find_install()


@pytest.fixture(autouse=True)
def _needs_install() -> None:
    if INSTALL is None:
        pytest.skip("the golden hashes were recorded against a local VCMI install")


def _generate(priors: Priors, config: StepConfig) -> MapState:
    pipeline = Pipeline(VcmiCatalog(), config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    return pipeline.run()


def _digest(state: MapState, out_dir: Path) -> str:
    path = VmapRenderer(str(out_dir), corpus_tiler()).render(state, "golden.vmap", name="golden")
    doc = VM.read(path)
    objects = sorted(json.dumps(dataclasses.asdict(o), sort_keys=True) for o in doc.objects)
    gate_blk = {str(lvl): sorted(tiles) for lvl, tiles in sorted(state.gate_blk.items())}
    idents = [(t, OB.identity_of(t.kind)) for t in state.player_towns]
    towns = [[t.x, t.y, t.level, i.type, i.subtype] for t, i in idents]
    payload = json.dumps(
        {"terrain": doc.terrain, "objects": objects, "gate_blk": gate_blk, "towns": towns},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _recorded() -> dict[str, str]:
    if not GOLDEN.exists():
        return {}
    loaded = jv.as_object(jv.loads(GOLDEN.read_text()))
    return {key: jv.as_str(value) for key, value in loaded.items()}


@pytest.mark.golden
@pytest.mark.parametrize(("key", "config"), MAPS, ids=[key for key, _config in MAPS])
def test_generated_map_matches_golden(
    key: str, config: StepConfig, priors: Priors, tmp_path: Path
) -> None:
    digest = _digest(_generate(priors, config), tmp_path)
    if os.environ.get("GOLDEN_UPDATE") == "1":
        recorded = _recorded()
        recorded[key] = digest
        _ = GOLDEN.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
        return
    assert _recorded().get(key) == digest
