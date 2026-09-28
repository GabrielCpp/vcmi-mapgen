from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.grid.pockets import Pockets
from vcmi_mapgen.core.model import Zone
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.steps.border.result import BorderResult
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.loot.result import LootResult
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.vegetation.result import VegetationResult
from vcmi_mapgen.corpus.priors import load_priors
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.renderers import PngRenderer, VmapRenderer
from vcmi_mapgen.renderers.overlays import (
    BlockingOverlay,
    GridOverlay,
    GuardOverlay,
    MapOverlay,
    PassageOverlay,
    PocketOverlay,
    TileTypeOverlay,
    ZoneOverlay,
)
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.install import VcmiInstall

ROOT = project_root()
CATALOG = VcmiCatalog()

# Every factory takes `pockets` (LootStep's LootResult.pockets) and `zones`
# (TerrainStep's Segmentation.zones) uniformly, even though only a few overlays use
# them -- they're disposable analysis, not a MapState fact
# (see vcmi_mapgen/core/model/AGENTS.md), so it must reach the overlay through its own
# constructor rather than the overlay reading/recomputing them off MapState.
#
# "zone" is fill-only here -- PngRenderer composites overlays in list order, so a
# zone-id label drawn at its normal stack position gets painted over by whatever
# overlay follows it. parse_overlays appends a second, label-only ZoneOverlay last
# whenever "zone" is requested, so the label always survives on top of the stack.


type Zones = Mapping[int, Mapping[int, Zone]]


def _zone(_pockets: Pockets, zones: Zones) -> MapOverlay:
    return ZoneOverlay(zones, labels=False)


def _blocking(_pockets: Pockets, _zones: Zones) -> MapOverlay:
    return BlockingOverlay(tiers=True)


def _passage(_pockets: Pockets, zones: Zones) -> MapOverlay:
    return PassageOverlay(zones)


def _pocket(pockets: Pockets, _zones: Zones) -> MapOverlay:
    return PocketOverlay(pockets)


def _guard(_pockets: Pockets, _zones: Zones) -> MapOverlay:
    return GuardOverlay()


def _grid(_pockets: Pockets, _zones: Zones) -> MapOverlay:
    return GridOverlay()


def _tile_type(_pockets: Pockets, _zones: Zones) -> MapOverlay:
    return TileTypeOverlay()


OVERLAY_FACTORIES: dict[str, Callable[[Pockets, Zones], MapOverlay]] = {
    "zone": _zone,
    "blocking": _blocking,
    "passage": _passage,
    "pocket": _pocket,
    "guard": _guard,
    "tile_type": _tile_type,
    "grid": _grid,
}
DEFAULT_OVERLAYS = "zone,blocking,guard,pocket,grid"
RENDERER_CHOICES = ("png", "vmap")
DEFAULT_RENDERERS = "png,vmap"


def parse_overlays(spec: str, pockets: Pockets, zones: Zones) -> list[MapOverlay]:
    spec = spec.strip().lower()
    names = [] if spec in ("", "none") else [s.strip() for s in spec.split(",")]
    unknown = [n for n in names if n not in OVERLAY_FACTORIES]
    if unknown:
        sys.exit(
            f"unknown overlay(s): {', '.join(unknown)} "
            + f"(choices: {', '.join(OVERLAY_FACTORIES)}, or 'none')"
        )
    overlays = [OVERLAY_FACTORIES[n](pockets, zones) for n in names if n != "grid"]
    if "zone" in names:
        overlays.append(ZoneOverlay(zones, fill=False))
    if "grid" in names:
        overlays.append(GridOverlay())
    return overlays


def _parse_renderers(spec: str) -> list[str]:
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in RENDERER_CHOICES]
    if unknown:
        sys.exit(
            f"unknown renderer(s): {', '.join(unknown)} (choices: {', '.join(RENDERER_CHOICES)})"
        )
    return names


@dataclass(frozen=True, slots=True)
class GenerateOptions:
    seed: int
    size: int
    players: int
    teams: str
    water_mode: str
    subterrain: bool
    overlays: str
    renderers: str
    stop_after: str | None


def generate(install: VcmiInstall, opts: GenerateOptions) -> None:
    pipeline = Pipeline(CATALOG, opts.size)
    config = StepConfig(opts.seed, opts.size, opts.players, opts.water_mode, opts.subterrain)
    for point_name, step in build_steps(load_priors(), config):
        _ = pipeline.add_step(step)
        if point_name == opts.stop_after:
            break
    map_state = pipeline.run()

    for line in (
        *pipeline.ctx.get(VegetationResult, VegetationResult()).log,
        *pipeline.ctx.get(BorderResult, BorderResult()).log,
        *pipeline.ctx.get(PortalResult, PortalResult()).log,
    ):
        print(f"  {line}")
    loot_result = pipeline.ctx.get(LootResult, LootResult())

    objs = map_state.objs
    veg_n = sum(1 for o in objs if not o.purpose)
    player_zids = pipeline.ctx.get(TownsIndex, TownsIndex()).player_zids
    print(
        f"generate s{opts.seed} {opts.size}x{opts.size}: "
        + f"{len(objs) - veg_n} gameplay+pickups, {veg_n} vegetation objects, "
        + f"towns={len(player_zids)}"
    )

    renderers = _parse_renderers(opts.renderers)

    if "png" in renderers:
        index = lod(install.data_dir)
        png_renderer = PngRenderer(index)
        png = os.path.join(str(ROOT), "out", "render", "pp", f"ppmap_s{opts.seed}.png")
        os.makedirs(os.path.dirname(png), exist_ok=True)
        png_renderer.render(map_state, level=0).save(png)
        print(f"  {png}")
        if opts.subterrain and 1 in map_state.terrain:
            png1 = png_renderer.save(map_state, f"ppmap_s{opts.seed}_L1.png", level=1)
            print(f"  {png1}")

        zones = pipeline.ctx.get(Segmentation, Segmentation({}, {})).zones
        overlays = parse_overlays(opts.overlays, loot_result.pockets, zones)
        if overlays:
            overlay_renderer = PngRenderer(index, overlays=overlays)
            ov_img = overlay_renderer.render(map_state, level=0)
            ov_png = os.path.join(
                str(ROOT), "out", "render", "pp", f"ppmap_s{opts.seed}_overlays.png"
            )
            os.makedirs(os.path.dirname(ov_png), exist_ok=True)
            ov_img.save(ov_png)
            print(f"  {ov_png}")

    if "vmap" in renderers:
        vmap_renderer = VmapRenderer(install=install)
        vmap = vmap_renderer.render(
            map_state,
            f"ppmap_s{opts.seed}.vmap",
            name=f"pp-map s{opts.seed}",
            teams_spec=opts.teams,
        )
        if map_state.player_towns:
            print(f"  playable: {len(map_state.player_towns)} players, victory=defeat-all")
        print(f"  {vmap}")
