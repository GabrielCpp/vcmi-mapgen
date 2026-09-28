"""End-to-end test of the render-sprites subcommand on a corpus map."""

from pathlib import Path

import pytest
from PIL import Image

from vcmi_mapgen.cli.render_sprites import render_sprites
from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.corpus.maps import corpus_path, load_corpus_map
from vcmi_mapgen.renderers.sprites import TILE
from vcmi_mapgen.vcmi.formats.lod import LOD_FILES
from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall

TEST_MAP = "All for One"


def _install() -> VcmiInstall | None:
    try:
        return load_settings().install()
    except InstallNotFoundError:
        return None


INSTALL = _install()
pytestmark = pytest.mark.skipif(
    INSTALL is None or not any((INSTALL.data_dir / f).exists() for f in LOD_FILES),
    reason="H3 sprite LOD files not found (set VCMI_HOME)",
)


def test_compare_renders_real_and_generated_side_by_side(tmp_path: Path) -> None:
    assert INSTALL is not None
    out = tmp_path / "side_by_side.png"
    render_sprites(INSTALL, corpus_path(TEST_MAP), compare=TEST_MAP, out=str(out))
    surf = load_corpus_map(TEST_MAP).surfs[0]
    with Image.open(out) as img:
        assert img.size == (2 * len(surf[0]) * TILE + 8, len(surf) * TILE)
