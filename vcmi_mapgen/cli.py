"""Learned procedural map generator for VCMI (one CLI, one pipeline).

Subcommands:
  generate        -> synthesize a full map via the marked-point-process pipeline
                     (CLI-selectable overlays/renderers/stop point).
  render-ontology -> render one sprite (+ passability mask overlay) per documented
                     ontology item — a documentation/debug tool, not part of the pipeline.

`generate` builds and runs a ``Pipeline`` (see ``pipeline.py``); `render-ontology` stays
outside that model entirely — it renders the object taxonomy itself, never touches a
generated map, and calls ``renderers.ontology_render`` directly.
"""
from __future__ import annotations

import argparse
import os
import sys

from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import Pipeline
from vcmi_mapgen.renderers import PngRenderer, VmapRenderer
from vcmi_mapgen.renderers.ontology_render import render_ontology
from vcmi_mapgen.renderers.overlays import (
    BlockingOverlay, GuardOverlay, PassageOverlay, PocketOverlay, TileTypeOverlay, ZoneOverlay,
)
from vcmi_mapgen.steps import (
    GameplayStep, GateStep, PickupStep, RepairStep, SegmentStep, TerrainStep, VegetationStep,
)
from vcmi_mapgen.steps.gameplay.step import GameplayIndex
from vcmi_mapgen.steps.repair.step import RepairResult

ROOT = project_root()
ONTOLOGY = Ontology()

GENERATE_STOP_POINTS = (
    "terrain", "segment", "gate", "gameplay", "vegetation", "pickup",
)

# Every factory takes `pockets` (RepairStep's RepairResult.pockets) uniformly, even
# though only PocketOverlay uses it -- it's disposable analysis, not a MapState fact
# (see vcmi_mapgen/models/AGENTS.md), so it must reach the overlay through its own
# constructor rather than the overlay reading/recomputing it off MapState.
_OVERLAY_FACTORIES = {
    "zone": lambda pockets: ZoneOverlay(),
    "blocking": lambda pockets: BlockingOverlay(tiers=True),
    "passage": lambda pockets: PassageOverlay(),
    "pocket": lambda pockets: PocketOverlay(pockets),
    "guard": lambda pockets: GuardOverlay(),
    "tile_type": lambda pockets: TileTypeOverlay(),
}
_DEFAULT_OVERLAYS = "zone,blocking,passage,guard,pocket"
_RENDERER_CHOICES = ("png", "vmap")
_DEFAULT_RENDERERS = "png,vmap"


def _parse_overlays(spec: str, pockets: dict):
    spec = spec.strip().lower()
    names = [] if spec in ("", "none") else [s.strip() for s in spec.split(",")]
    unknown = [n for n in names if n not in _OVERLAY_FACTORIES]
    if unknown:
        sys.exit(f"unknown overlay(s): {', '.join(unknown)} "
                 f"(choices: {', '.join(_OVERLAY_FACTORIES)}, or 'none')")
    return [_OVERLAY_FACTORIES[n](pockets) for n in names]


def _parse_renderers(spec: str):
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in _RENDERER_CHOICES]
    if unknown:
        sys.exit(f"unknown renderer(s): {', '.join(unknown)} "
                 f"(choices: {', '.join(_RENDERER_CHOICES)})")
    return names


def cmd_render_ontology(args):
    render_ontology(args.out)


def _generate_steps(args, water_mode):
    """(name, step) pairs in run order. `name` matches GENERATE_STOP_POINTS so the CLI
    can truncate the list at the requested --stop-after point; Pipeline itself has no
    concept of a stop point."""
    steps = [
        ("terrain", TerrainStep(size=args.size, seed=args.seed,
                                water_mode=water_mode, subterrain=args.subterrain)),
        ("segment", SegmentStep()),
    ]
    if args.subterrain:
        steps.append(("gate", GateStep(seed=args.seed)))
    steps.append(("gameplay", GameplayStep(seed=args.seed, players=args.players,
                                           size=args.size, subterrain=args.subterrain)))
    steps.append(("vegetation", VegetationStep(seed=args.seed)))
    steps.append(("pickup", PickupStep(seed=args.seed, size=args.size)))
    steps.append(("repair", RepairStep(seed=args.seed, size=args.size,
                                       subterrain=args.subterrain)))
    return steps


def cmd_generate(args):
    if args.stop_after == "gate" and not args.subterrain:
        sys.exit("--stop-after gate requires --subterrain (no GateStep otherwise)")
    wmode = args.water_mode or ("none" if args.no_water else "normal")

    pipeline = Pipeline(ONTOLOGY)
    for point_name, step in _generate_steps(args, wmode):
        pipeline.add_step(step)
        if point_name == args.stop_after:
            break
    map_state = pipeline.run()

    repair_result = pipeline.ctx.get(RepairResult, RepairResult())
    for line in repair_result.log:
        print(f"  {line}")

    objs = map_state.objs
    veg_n = sum(1 for o in objs if not o.get("purpose"))
    player_zids = pipeline.ctx.get(GameplayIndex, GameplayIndex()).player_zids
    print(f"generate s{args.seed} {args.size}x{args.size}: "
          f"{len(objs) - veg_n} gameplay+pickups, {veg_n} vegetation objects, "
          f"towns={len(player_zids)}")

    renderers = _parse_renderers(args.renderers)

    if "png" in renderers:
        png_renderer = PngRenderer()
        png = os.path.join(ROOT, "out", "render", "pp", f"ppmap_s{args.seed}.png")
        os.makedirs(os.path.dirname(png), exist_ok=True)
        png_renderer.render(map_state, level=0).save(png)
        print(f"  {png}")
        if args.subterrain and 1 in map_state.cells:
            png1 = png_renderer.save(map_state, f"ppmap_s{args.seed}_L1.png", level=1)
            print(f"  {png1}")

        overlays = _parse_overlays(args.overlays, repair_result.pockets)
        if overlays:
            overlay_renderer = PngRenderer(overlays=overlays)
            ov_img = overlay_renderer.render(map_state, level=0)
            ov_png = os.path.join(ROOT, "out", "render", "pp", f"ppmap_s{args.seed}_overlays.png")
            os.makedirs(os.path.dirname(ov_png), exist_ok=True)
            ov_img.save(ov_png)
            print(f"  {ov_png}")

    if "vmap" in renderers:
        vmap_renderer = VmapRenderer()
        vmap = vmap_renderer.render(map_state, f"ppmap_s{args.seed}.vmap",
                                    name=f"pp-map s{args.seed}", teams_spec=args.teams)
        if map_state.player_towns:
            print(f"  playable: {len(map_state.player_towns)} players, victory=defeat-all")
        print(f"  {vmap}")


def main():
    ap = argparse.ArgumentParser(description="Learned procedural map generator for VCMI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pro = sub.add_parser("render-ontology",
                         help="render one sprite per documented ontology item to "
                              "out/ontology/<CLUSTER>/<terrain>/<type>.png")
    pro.add_argument("--out", default=None, help="output dir (default out/ontology)")
    pro.set_defaults(func=cmd_render_ontology)

    pg = sub.add_parser("generate", help="full map synthesized by the marked-point-process pipeline")
    pg.add_argument("--seed", type=int, default=0)
    pg.add_argument("--size", type=int, default=72, help="W=H of the generated map")
    pg.add_argument("--no-water", action="store_true", dest="no_water",
                    help="reassign water tiles to the nearest land terrain (land-only map)")
    pg.add_argument("--players", type=int, default=2,
                    help="number of players; the N largest zones get start towns")
    pg.add_argument("--teams", default="ffa",
                    help="team matrix: 'ffa', '2v2'-style, or explicit '0,0,1,1'")
    pg.add_argument("--water-mode", choices=["none", "normal", "islands"], default=None,
                    dest="water_mode", help="water style")
    pg.add_argument("--subterrain", action="store_true",
                    help="add a second, underground level connected to the surface by "
                         "Subterranean Gate pairs")
    pg.add_argument("--overlays", default=_DEFAULT_OVERLAYS,
                    help=f"comma-separated overlays to render on the PNG output "
                         f"(choices: {', '.join(_OVERLAY_FACTORIES)}; 'none' to disable) "
                         f"(default: {_DEFAULT_OVERLAYS})")
    pg.add_argument("--renderers", default=_DEFAULT_RENDERERS,
                    help=f"comma-separated renderer(s) to run "
                         f"(choices: {', '.join(_RENDERER_CHOICES)}) "
                         f"(default: {_DEFAULT_RENDERERS})")
    pg.add_argument("--stop-after", choices=GENERATE_STOP_POINTS, default=None,
                    dest="stop_after",
                    help="stop the pipeline early, right after the named step (debug), "
                         "instead of running the full pipeline through RepairStep")
    pg.set_defaults(func=cmd_generate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
