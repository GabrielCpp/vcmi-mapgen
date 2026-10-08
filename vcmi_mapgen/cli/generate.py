from __future__ import annotations

import json
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import DEFAULT_VEGETATION, StepConfig, build_steps
from vcmi_mapgen.core.grid.pockets import Pockets
from vcmi_mapgen.core.model import Zone
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.steps.gameplay.result import TownsIndex
from vcmi_mapgen.core.steps.loot.result import LootResult
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.vegetation.result import VegetationResult
from vcmi_mapgen.corpus.priors import load_priors
from vcmi_mapgen.corpus.tiler import load_tiler
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
from vcmi_mapgen.vcmi.content.enabled import (
    BASE_CONTENT,
    ContentConflictError,
    ContentSetting,
    UnknownModError,
    enable,
)
from vcmi_mapgen.vcmi.content.manifest import read_manifests
from vcmi_mapgen.vcmi.content.mods import load_mods
from vcmi_mapgen.vcmi.content.sprites import SpriteSource
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.install import VcmiInstall

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
INSTALL_FOLDER = "pp-gen"


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
    vegetation: str
    content: ContentSetting = BASE_CONTENT
    density: float = 1.0
    name: str | None = None
    install: bool = False


@dataclass(frozen=True, slots=True)
class VegetationRenderOptions:
    seeds: Sequence[int]
    size: int
    players: int
    water_mode: str
    subterrain: bool
    overlays: str
    vegetation: str
    content: ContentSetting = BASE_CONTENT


def open_catalog(install: VcmiInstall, setting: ContentSetting) -> VcmiCatalog:
    """The catalog of the content the user enabled. A mod that is not installed, or two
    enabled mods that conflict, stop generation with a message."""
    manifests = read_manifests(install.mods_dir) if setting.mods else {}
    try:
        enabled = enable(setting, manifests)
    except (UnknownModError, ContentConflictError) as e:
        sys.exit(f"content setting refused: {e}")
    return VcmiCatalog(enabled, load_mods(manifests, enabled))


def sprite_source(install: VcmiInstall, catalog: VcmiCatalog) -> SpriteSource:
    """The sprites of the base game, then of each mod the catalog holds."""
    return SpriteSource(lod(install.data_dir), catalog.mods.archives())


def _run_pipeline(
    catalog: VcmiCatalog, settings: Settings, config: StepConfig, stop_after: str | None
) -> Pipeline:
    pipeline = Pipeline(catalog, config.size)
    for point_name, step in build_steps(
        load_priors(settings.pp_dir, settings.pockets_file), config
    ):
        _ = pipeline.add_step(step)
        if point_name == stop_after:
            break
    _ = pipeline.run()
    return pipeline


def render_vegetation(
    install: VcmiInstall, settings: Settings, opts: VegetationRenderOptions
) -> None:
    """Run the pipeline through the vegetation step for each seed and save one PNG of the
    terrain and the vegetation per level to out/render/vegetation/."""
    out = settings.out_dir / "render" / "vegetation"
    os.makedirs(out, exist_ok=True)
    tables = load_tiler(settings.pp_dir)
    catalog = open_catalog(install, opts.content)
    index = sprite_source(install, catalog)
    for seed in opts.seeds:
        config = StepConfig(
            seed,
            opts.size,
            opts.players,
            opts.water_mode,
            opts.subterrain,
            opts.vegetation,
        )
        pipeline = _run_pipeline(catalog, settings, config, "vegetation")
        map_state = pipeline.map_state
        zones = pipeline.ctx.get(Segmentation, Segmentation({}, {})).zones
        renderer = PngRenderer(index, str(out), tables, parse_overlays(opts.overlays, {}, zones))
        print(f"vegetation s{seed} ({opts.vegetation}): {len(map_state.objs)} objects")
        for level in sorted(map_state.terrain):
            suffix = "" if level == 0 else f"_L{level}"
            name = f"veg_s{seed}_{opts.vegetation}{suffix}.png"
            print(f"  {renderer.save(map_state, name, level=level)}")


def file_stem(name: str) -> str:
    """The file name a map title gives, with the characters a file system refuses replaced."""
    stem = re.sub(r'[\\/:*?"<>|]', "_", name).strip(" .")
    if not stem:
        sys.exit(f"map name {name!r} gives no usable file name")
    return stem


def install_map(vmap: str, install: VcmiInstall) -> Path:
    """Copy a written .vmap into the install's ``Maps/pp-gen`` folder, where VCMI lists it."""
    folder = install.maps_dir / INSTALL_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(vmap, folder / Path(vmap).name))


def map_folder(opts: GenerateOptions) -> str:
    """The name of the folder that holds one map's files, and of its .vmap: the map name
    when the user gave one, otherwise the seed, the size and a vegetation tag when the
    sampler is not the default."""
    if opts.name is not None:
        return file_stem(opts.name)
    stem = f"ppmap_s{opts.seed}_{opts.size}"
    if opts.vegetation != DEFAULT_VEGETATION:
        stem = f"{stem}_{opts.vegetation}"
    return stem


def fresh_folder(out_dir: Path, name: str) -> Path:
    """The folder ``out_dir/name``, emptied of every file an earlier run left. A name that
    leads outside ``out_dir`` stops generation with a message."""
    folder = out_dir / name
    if folder.resolve().parent != out_dir.resolve():
        sys.exit(f"map folder {name!r} is not directly under {out_dir}")
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    return folder


def run_record(opts: GenerateOptions) -> dict[str, object]:
    """The seed, the size and every generate flag, enough to rebuild the same map."""
    record: dict[str, object] = asdict(opts)
    record["content"] = {
        "mods": sorted(opts.content.mods),
        "banned": sorted(opts.content.banned),
    }
    return record


def write_run(folder: Path, opts: GenerateOptions) -> Path:
    """Write ``run.json`` into the map's folder and return its path."""
    path = folder / "run.json"
    _ = path.write_text(json.dumps(run_record(opts), indent=2, sort_keys=True) + "\n")
    return path


def generate(install: VcmiInstall, settings: Settings, opts: GenerateOptions) -> None:
    renderers = _parse_renderers(opts.renderers)
    if opts.install and "vmap" not in renderers:
        sys.exit("--install needs the vmap renderer")
    config = StepConfig(
        opts.seed,
        opts.size,
        opts.players,
        opts.water_mode,
        opts.subterrain,
        opts.vegetation,
        opts.density,
    )
    catalog = open_catalog(install, opts.content)
    pipeline = _run_pipeline(catalog, settings, config, opts.stop_after)
    map_state = pipeline.map_state

    for line in (
        *pipeline.ctx.get(VegetationResult, VegetationResult()).log,
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

    tables = load_tiler(settings.pp_dir)
    stem = map_folder(opts)
    folder = fresh_folder(settings.out_dir, stem)
    print(f"  {write_run(folder, opts)}")

    if "png" in renderers:
        index = sprite_source(install, catalog)
        png_renderer = PngRenderer(index, str(folder), tables)
        print(f"  {png_renderer.save(map_state, 'surface.png', level=0)}")
        if opts.subterrain and 1 in map_state.terrain:
            print(f"  {png_renderer.save(map_state, 'underground.png', level=1)}")

        zones = pipeline.ctx.get(Segmentation, Segmentation({}, {})).zones
        overlays = parse_overlays(opts.overlays, loot_result.pockets, zones)
        if overlays:
            overlay_renderer = PngRenderer(index, str(folder), tables, overlays)
            print(f"  {overlay_renderer.save(map_state, 'overlays.png', level=0)}")

    if "vmap" in renderers:
        vmap_renderer = VmapRenderer(str(folder), tables, install, catalog.mods)
        vmap = vmap_renderer.render(
            map_state,
            f"{stem}.vmap",
            name=opts.name or f"pp-map s{opts.seed}",
            teams_spec=opts.teams,
        )
        if map_state.player_towns:
            print(f"  playable: {len(map_state.player_towns)} players, victory=defeat-all")
        print(f"  {vmap}")
        if opts.install:
            print(f"  installed: {install_map(vmap, install)}")
