"""Shape-driven zone-rebuilding engine + learned terrain generator (one unified CLI).

Records each terrain zone's object pattern in a shape-relative frame and replays it.
The hard contract: rebuilding on the SAME shape reproduces the EXACT same objects
(bit-exact, integer-only); a DIFFERENT shape gets a sensible warp adaptation.

Subcommands:
  extract         -> segment a map into same-terrain zones, label them, dump a template JSON
  inspect         -> zone-tint + label segmentation PNG (per level)
  features        -> per-zone feature profile (density/depth/spacing) JSON
  rebuild         -> template + target terrain -> editor .vmap
                     --identity [--verify]   exact reconstruction on the source terrain
                     --zone N --deform       rough warp of one zone onto a deformed shape
  run             -> extract -> segmentation -> identity rebuild+verify -> realistic editor
                     render, then STOP for manual inspection (the foundation checkpoint).
  generate        -> synthesize a full map via the marked-point-process pipeline
                     (the only subcommand with CLI-selectable overlays/renderers/stop point).
  render-ontology -> render one sprite (+ passability mask overlay) per documented
                     ontology item — a documentation/debug tool, not part of any pipeline.

Each subcommand builds and runs its own ``Pipeline`` (see ``pipeline.py``) except
`extract`/`inspect`/`features`/`render-ontology`, which call the rebuild engine's
functions directly and never go through a pipeline at all; `generate` additionally
accepts --overlays/--renderers/--stop-after.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import vmap as VM
from vcmi_mapgen.kit.paths import project_root, slug
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.pipeline import Pipeline
from vcmi_mapgen.rebuild import report as REPORT
from vcmi_mapgen.rebuild.engine import _prio, fm_to_document, write_features, write_template
from vcmi_mapgen.rebuild.render import editor_render, render_segmentation
from vcmi_mapgen.renderers import PngRenderer, VmapRenderer
from vcmi_mapgen.renderers.ontology_render import render_ontology
from vcmi_mapgen.renderers.overlays import (
    BlockingOverlay, GuardOverlay, PassageOverlay, PocketOverlay, TileTypeOverlay, ZoneOverlay,
)
from vcmi_mapgen.steps import (
    DeformWarpStep, ExtractTemplateStep, FmDocumentStep, GameplayStep, GateStep,
    PickupStep, RebuildMapStep, RepairStep, SegmentStep, TerrainGenStep, TileStep,
    VegetationStep, VerifyStep,
)

ROOT = project_root()
ONTOLOGY = Ontology()

GENERATE_STOP_POINTS = (
    "terrain_gen", "tile", "segment", "gate", "gameplay", "vegetation", "pickup",
)

# Every factory takes `pockets` (RepairStep's ctx["pockets"]) uniformly, even though
# only PocketOverlay uses it -- it's disposable analysis, not a MapState fact (see
# vcmi_mapgen/models/AGENTS.md), so it must reach the overlay through its own
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


def cmd_extract(args):
    path, t = write_template(args.name, args.out)
    nz = sum(len(l["zones"]) for l in t["levels"])
    nbar = sum(len(l["barrier_objects"]) for l in t["levels"])
    print(f"extracted {t['name']}: {len(t['levels'])} levels, {nz} zones, "
          f"{nbar} barrier objects -> {path}")


def cmd_render_ontology(args):
    render_ontology(args.out)


def cmd_inspect(args):
    out = os.path.join(ROOT, "out", "render", f"{slug(args.name)}_segmentation.png")
    path, tables = render_segmentation(args.name, out)
    REPORT.print_zone_tables(tables)
    print(f"\nsegmentation -> {path}")


def cmd_features(args):
    out, f = write_features(args.name, args.out)
    for lvl in f["levels"]:
        for z in lvl["zones"]:
            if args.zone is not None and z["zone_id"] != args.zone:
                continue
            print(f"\nL{lvl['level']} zone {z['zone_id']}  {z['label']}  "
                  f"area={z['area']}  guard->loot={z['guard_loot_dist']}")
            for p in sorted(z["purposes"], key=_prio):
                i = z["purposes"][p]
                print(f"  {p:<15} n={i['count']:<4} dens={i['density']:.4f} "
                      f"depth={i['depth_mu']:.2f}±{i['depth_sd']:.2f} "
                      f"spacing={i['spacing']:<4} variants={len(i['identities'])}")
    print(f"\nfeatures -> {out}")


def _run_identity_rebuild(name: str, out_name: str, verify: bool = False) -> Pipeline:
    """extract -> rebuild (identity) -> [verify] -> fm_document. Returns the Pipeline;
    read ``template``/``fm``/``stats``/``verify``/``document`` off ``pipeline.ctx``."""
    src = OR.load_faithful(name)
    pipeline = Pipeline(ONTOLOGY)
    pipeline.ctx["target_terrain"] = src["terrain"]
    pipeline.add_step(ExtractTemplateStep(name))
    pipeline.add_step(RebuildMapStep(identity=True))
    if verify:
        pipeline.add_step(VerifyStep(name))
    pipeline.add_step(FmDocumentStep(out_name))
    pipeline.run()
    return pipeline


def _run_deform_rebuild(name: str, zone_id: int, out_name: str) -> Pipeline:
    """extract -> deform_warp -> fm_document. Returns the Pipeline; read ``template``/
    ``fm``/``document`` off ``pipeline.ctx``."""
    pipeline = Pipeline(ONTOLOGY)
    pipeline.add_step(ExtractTemplateStep(name))
    pipeline.add_step(DeformWarpStep(name, zone_id))
    pipeline.add_step(FmDocumentStep(out_name))
    pipeline.run()
    return pipeline


def cmd_rebuild(args):
    stem = args.out or os.path.join(ROOT, "out", f"Rebuilt-{args.name.replace(' ', '_')}")
    if args.deform:
        if args.zone is None:
            sys.exit("--deform requires --zone N")
        pipeline = _run_deform_rebuild(args.name, args.zone, os.path.basename(stem))
    else:
        pipeline = _run_identity_rebuild(args.name, os.path.basename(stem),
                                         verify=args.verify)
        stats, fm = pipeline.ctx["stats"], pipeline.ctx["fm"]
        print(f"identity rebuild: {stats['identity']} zones matched, "
              f"{stats['missing']} missing, {len(fm['objects'])} objects")
        verify_result = pipeline.ctx.get("verify")
        if verify_result is not None:
            REPORT.report_verify(*verify_result)

    VM.write(pipeline.ctx["document"], stem + ".vmap")
    print(f"wrote {stem}.vmap")


def cmd_run(args):
    name = args.name
    print(f"=== run: {name} ===")

    pipeline = _run_identity_rebuild(name, f"Rebuilt-{name.replace(' ', '_')}", verify=True)
    template = pipeline.ctx["template"]
    stats = pipeline.ctx["stats"]
    document = pipeline.ctx["document"]
    verify_result = pipeline.ctx["verify"]

    tpath = os.path.join(ROOT, "out", f"zone_template-{slug(name)}.json")
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    json.dump(template, open(tpath, "w"))
    print(f"[1/4] extracted template -> {tpath}")

    seg = os.path.join(ROOT, "out", "render", f"{slug(name)}_segmentation.png")
    _, tables = render_segmentation(name, seg)
    REPORT.print_zone_tables(tables)
    print(f"[2/4] segmentation -> {seg}")

    stem = os.path.join(ROOT, "out", f"Rebuilt-{name.replace(' ', '_')}")
    VM.write(document, stem + ".vmap")
    print(f"[3/4] identity rebuild ({stats['identity']} zones, "
          f"{stats['missing']} missing) -> {stem}.vmap")
    ok = REPORT.report_verify(*verify_result)

    # Honest visual: render REBUILT against the SOURCE faithful via the SAME path
    # (the .h3m read path over-draws underground sprites onto the surface).
    src = OR.load_faithful(name)
    src_vmap = os.path.join(ROOT, "out", f"_Source-{name.replace(' ', '_')}.vmap")
    VM.write(fm_to_document(src, name=f"Source-{name}"), src_vmap)
    edit = os.path.join(ROOT, "out", "render", f"{slug(name)}_identity_editor.png")
    editor_render(stem + ".vmap", edit, compare_vmap=src_vmap)
    print(f"[4/4] realistic editor render (SOURCE | REBUILT, surface) -> {edit}")

    print("\n>>> INSPECTION CHECKPOINT <<<")
    print(f"  identity guarantee: {'PASS (bit-exact)' if ok else 'FAIL — see above'}")
    print(f"  inspect: {seg}")
    print(f"           {edit}  (the two surfaces should be visually identical)")
    print("  underground objects are covered by --verify but not by the surface render.")


def _generate_steps(args, water_mode):
    """(name, step) pairs in run order. `name` matches GENERATE_STOP_POINTS so the CLI
    can truncate the list at the requested --stop-after point; Pipeline itself has no
    concept of a stop point."""
    steps = [
        ("terrain_gen", TerrainGenStep(size=args.size, seed=args.seed,
                                       water_mode=water_mode, subterrain=args.subterrain)),
        ("tile", TileStep(size=args.size)),
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

    for line in pipeline.ctx.get("log", []):
        print(f"  {line}")

    objs = map_state.objs
    veg_n = sum(1 for o in objs if not o.get("purpose"))
    player_zids = pipeline.ctx.get("player_zids", [])
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

        overlays = _parse_overlays(args.overlays, pipeline.ctx.get("pockets", {}))
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
    ap = argparse.ArgumentParser(description="Shape-driven zone-rebuilding engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="map -> template JSON")
    pe.add_argument("name")
    pe.add_argument("--out", default=None)
    pe.set_defaults(func=cmd_extract)

    pro = sub.add_parser("render-ontology",
                         help="render one sprite per documented ontology item to "
                              "out/ontology/<CLUSTER>/<terrain>/<type>.png")
    pro.add_argument("--out", default=None, help="output dir (default out/ontology)")
    pro.set_defaults(func=cmd_render_ontology)

    pi = sub.add_parser("inspect", help="segmentation + labels PNG")
    pi.add_argument("name")
    pi.set_defaults(func=cmd_inspect)

    pf = sub.add_parser("features", help="per-zone feature profile (the 'understanding')")
    pf.add_argument("name")
    pf.add_argument("--zone", type=int, default=None)
    pf.add_argument("--out", default=None)
    pf.set_defaults(func=cmd_features)

    pr = sub.add_parser("rebuild", help="rebuild objects onto target terrain")
    pr.add_argument("name")
    pr.add_argument("--identity", action="store_true", help="rebuild on the source terrain")
    pr.add_argument("--verify", action="store_true", help="assert bit-exact identity")
    pr.add_argument("--zone", type=int, default=None, help="zone id for --deform")
    pr.add_argument("--deform", action="store_true", help="rough warp onto a deformed shape")
    pr.add_argument("--out", default=None, help="output stem (no extension)")
    pr.set_defaults(func=cmd_rebuild)

    prun = sub.add_parser("run", help="foundation pipeline to the inspection checkpoint")
    prun.add_argument("name")
    prun.set_defaults(func=cmd_run)

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
