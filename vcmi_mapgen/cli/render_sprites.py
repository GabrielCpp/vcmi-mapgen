import os

from PIL import Image

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.corpus.maps import corpus_path, load_corpus_map
from vcmi_mapgen.renderers.sprites import render_map
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.install import VcmiInstall
from vcmi_mapgen.vcmi.load import load_map, map_colours


def _flags(vmap: str) -> dict[tuple[int, int], str]:
    return {(x, y): c for (x, y, level), c in map_colours(vmap).items() if level == 0}


def render_sprites(
    install: VcmiInstall,
    settings: Settings,
    vmap: str,
    compare: str | None = None,
    out: str | None = None,
) -> None:
    index = lod(install.data_dir)
    gen = load_map(vmap)
    surf, objs = VM.read(vmap).terrain[0], gen.objs
    gen_img = render_map(index, surf, objs, os.path.basename(vmap), _flags(vmap))

    if compare:
        real = load_corpus_map(settings.maps_dir, compare)
        rsurf, robjs = VM.read(corpus_path(settings.maps_dir, compare)).terrain[0], real.objs
        real_path = corpus_path(settings.maps_dir, compare)
        real_img = render_map(index, rsurf, robjs, f"REAL: {compare}", _flags(real_path))
        gap = 8
        canvas = Image.new(
            "RGB",
            (real_img.width + gap + gen_img.width, max(real_img.height, gen_img.height)),
            (0, 0, 0),
        )
        canvas.paste(real_img, (0, 0))
        canvas.paste(gen_img, (real_img.width + gap, 0))
        out_img = canvas
    else:
        out_img = gen_img

    out_path = out or os.path.join(
        settings.out_dir, "render", os.path.basename(vmap).replace(".vmap", "_editor.png")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_img.save(out_path)
    print(f"wrote {out_path}  ({out_img.width}x{out_img.height})")
