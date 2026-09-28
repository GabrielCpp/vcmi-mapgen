import os

from PIL import Image

from vcmi_mapgen.corpus.maps import corpus_path, load_corpus_map
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.renderers.sprites import render_map
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.install import VcmiInstall
from vcmi_mapgen.vcmi.load import load_map


def render_sprites(
    install: VcmiInstall, vmap: str, compare: str | None = None, out: str | None = None
) -> None:
    index = lod(install.data_dir)
    gen = load_map(vmap)
    surf, objs = VM.read(vmap).terrain[0], gen.objs
    gen_img = render_map(index, surf, objs, title=os.path.basename(vmap))

    if compare:
        real = load_corpus_map(compare)
        rsurf, robjs = VM.read(corpus_path(compare)).terrain[0], real.objs
        real_img = render_map(index, rsurf, robjs, title=f"REAL: {compare}")
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
        project_root(), "out", "render", os.path.basename(vmap).replace(".vmap", "_editor.png")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_img.save(out_path)
    print(f"wrote {out_path}  ({out_img.width}x{out_img.height})")
