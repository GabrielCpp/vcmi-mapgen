"""End-to-end test of the render-sprites subcommand on a corpus map."""

from pathlib import Path

import pytest
from PIL import Image

from vcmi_mapgen.cli.render_sprites import render_sprites
from vcmi_mapgen.conftest import SETTINGS, corpus_map_path, find_install
from vcmi_mapgen.renderers.sprites import TILE
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.lod import LOD_FILES

TEST_MAP = "All for One"


INSTALL = find_install()
pytestmark = pytest.mark.skipif(
    INSTALL is None or not any((INSTALL.data_dir / f).exists() for f in LOD_FILES),
    reason="H3 sprite LOD files not found (set VCMI_HOME)",
)


def test_compare_renders_real_and_generated_side_by_side(tmp_path: Path) -> None:
    assert INSTALL is not None
    out = tmp_path / "side_by_side.png"
    path = str(corpus_map_path(TEST_MAP))
    render_sprites(INSTALL, SETTINGS, path, compare=TEST_MAP, out=str(out))
    surf = VM.read(path).terrain[0]
    with Image.open(out) as img:
        assert img.size == (2 * len(surf[0]) * TILE + 8, len(surf) * TILE)
