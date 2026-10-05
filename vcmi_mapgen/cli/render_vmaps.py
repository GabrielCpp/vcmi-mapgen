"""Render every `.vmap` of a folder to PNGs with real sprites, each map's own tile art kept.

The surface lands at `<png_dir>/<name>.png` and the underground of a two-level map at
`<png_dir>/<name>_underground.png`.
"""

from pathlib import Path

from vcmi_mapgen.corpus.maps import all_map_names, corpus_path, load_corpus_map
from vcmi_mapgen.renderers import PngRenderer
from vcmi_mapgen.vcmi.formats import vmap as VM

UNDERGROUND_SUFFIX = "_underground"


def render_vmap(renderer: PngRenderer, vmap_dir: Path, png_dir: Path, name: str) -> list[Path]:
    """Render one map's levels and return the paths written."""
    state = load_corpus_map(vmap_dir, name)
    doc = VM.read(corpus_path(vmap_dir, name))
    written: list[Path] = []
    for level, surface in enumerate(doc.terrain):
        path = png_dir / f"{name}{UNDERGROUND_SUFFIX if level else ''}.png"
        renderer.render(state, level, name, surface).save(path)
        written.append(path)
    return written


def render_vmaps(renderer: PngRenderer, vmap_dir: Path, png_dir: Path) -> None:
    """Render every map in ``vmap_dir`` and print each failure and the count rendered."""
    png_dir.mkdir(parents=True, exist_ok=True)
    names = all_map_names(vmap_dir)
    ok = 0
    for name in names:
        try:
            _ = render_vmap(renderer, vmap_dir, png_dir, name)
        except Exception as e:
            print("RENDER FAIL", name, e)
            continue
        ok += 1
    print(f"rendered {ok}/{len(names)} maps to {png_dir}")
