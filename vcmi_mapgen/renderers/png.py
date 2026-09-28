"""PngRenderer — render a MapState level to a PIL Image using H3 sprites."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable

from PIL import Image

import vcmi_mapgen.renderers.sprites as RED
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.renderers.overlays.base import MapOverlay
from vcmi_mapgen.vcmi.formats.lod import LodIndex

ROOT = project_root()


class PngRenderer:
    """Render a MapState to editor-quality 32px H3 sprite PNGs.

    Overlays are RGBA layers composited over the base sprite render; any number
    of overlay instances can be stacked in order.

    Usage::

        renderer = PngRenderer(lod(install.data_dir), out_dir="out/render/pp")
        img = renderer.render(state, level=0)          # returns PIL Image
        path = renderer.save(state, "mymap.png")       # saves and returns path

        from vcmi_mapgen.renderers.overlays import ZoneOverlay, BlockingOverlay
        renderer = PngRenderer(index, overlays=[ZoneOverlay(), BlockingOverlay()])
    """

    index: LodIndex
    out_dir: str
    _overlays: list[MapOverlay]

    def __init__(
        self, index: LodIndex, out_dir: str | None = None, overlays: Iterable[MapOverlay] = ()
    ) -> None:
        self.index = index
        self.out_dir = out_dir or str(ROOT / "out" / "render" / "pp")
        self._overlays = list(overlays)

    def render(self, state: MapState, level: int = 0, title: str = "") -> Image.Image:
        """Return a PIL Image for the given level, with overlays composited."""
        surfs = state.surfs.get(level)
        if surfs is None:
            raise ValueError(f"state.surfs has no level {level}")
        if level == 0:
            objs = [o for o in state.objs if o.level == 0]
        else:
            # renderers.sprites draws only l==0 objects; shift underground to l=0
            objs = [dataclasses.replace(o, level=0) for o in state.objs if o.level == level]
        base = RED.render_map(self.index, surfs, objs, title=title)
        if not self._overlays:
            return base
        img = base.convert("RGBA")
        for overlay in self._overlays:
            img = Image.alpha_composite(img, overlay.apply(state, level))
        return img.convert("RGB")

    def save(self, state: MapState, path: str, level: int = 0, title: str = "") -> str:
        """Render and save to *path*. Returns the resolved path."""
        if not os.path.isabs(path):
            path = os.path.join(self.out_dir, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = self.render(state, level=level, title=title)
        img.save(path)
        return path
