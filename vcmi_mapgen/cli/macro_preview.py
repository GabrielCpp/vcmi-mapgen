"""Preview one macro terrain grid: print the corpus macro statistics and the generated
grid's zone report, and render the grid to ``out/render/pp/macro_s<seed>.png``.

    uv run python -m vcmi_mapgen.cli.macro_preview --seed 3 --size 72
"""

import argparse
import os

from PIL import Image

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.terrain_gen.macro import MacroOptions, generate, report
from vcmi_mapgen.corpus.priors import load_priors
from vcmi_mapgen.renderers.palette import TERRAIN_RGB
from vcmi_mapgen.renderers.palette import TERRAIN_TILE_PX as _TILE


class _Args(argparse.Namespace):
    seed: int = 3
    size: int = 72
    water: float | None = None
    level: int = 0


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("--seed", type=int, default=3)
    _ = ap.add_argument("--size", type=int, default=72)
    _ = ap.add_argument("--water", type=float, default=None)
    _ = ap.add_argument("--level", type=int, default=0, help="0=surface, 1=underground")
    args = ap.parse_args(namespace=_Args())
    settings = load_settings()
    priors = load_priors(settings.pp_dir, settings.pockets_file).terrain[args.level]
    st = priors.macro
    barrier_name = "water" if args.level == 0 else "rock"
    median_area = st.areas[len(st.areas) // 2]
    median_frac = st.barrier_fracs[len(st.barrier_fracs) // 2]
    head = f"macro stats (level {args.level}): {len(st.areas)} corpus zones"
    tail = f"median area {median_area}, median {barrier_name} frac {median_frac:.2f}"
    print(f"{head}, {tail}")
    grid = generate(args.size, args.seed, priors, MacroOptions(water=args.water, level=args.level))
    print("generated:", report(grid))
    img = Image.new("RGB", (args.size * _TILE, args.size * _TILE))
    for y, row in enumerate(grid):
        for x, t in enumerate(row):
            box = (x * _TILE, y * _TILE, (x + 1) * _TILE, (y + 1) * _TILE)
            img.paste(TERRAIN_RGB[Terrain(t)], box)
    out = str(settings.out_dir / "render" / "pp" / f"macro_s{args.seed}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print("->", out)


if __name__ == "__main__":
    main()
