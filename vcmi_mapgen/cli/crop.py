"""The crop subcommand: one map PNG cut down to the tiles around one tile."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.renderers.sprites import TILE

MARK = (255, 0, 255)


def crop_path(png: Path, at: Tile, around: int) -> Path:
    x, y = at
    return png.with_name(f"{png.stem}_crop_{x}_{y}_r{around}.png")


def crop(png: Path, at: Tile, around: int, out: Path | None = None) -> Path:
    """Save the tiles within ``around`` of ``at``, with ``at`` outlined, and return the path."""
    x, y = at
    with Image.open(png) as img:
        cols, rows = img.width // TILE, img.height // TILE
        if not (0 <= x < cols and 0 <= y < rows):
            raise SystemExit(f"{x},{y} is off the {cols}x{rows} map in {png}")
        left, top = max(0, x - around), max(0, y - around)
        right, bottom = min(cols, x + around + 1), min(rows, y + around + 1)
        piece = img.crop((left * TILE, top * TILE, right * TILE, bottom * TILE)).convert("RGB")
    ox, oy = (x - left) * TILE, (y - top) * TILE
    ImageDraw.Draw(piece).rectangle((ox, oy, ox + TILE - 1, oy + TILE - 1), outline=MARK, width=2)
    path = out or crop_path(png, at, around)
    path.parent.mkdir(parents=True, exist_ok=True)
    piece.save(path)
    print(
        f"wrote {path}  ({piece.width}x{piece.height}, tiles x {left}..{right - 1}, "
        + f"y {top}..{bottom - 1})"
    )
    return path
