"""Learned procedural map generator for VCMI (one CLI, one pipeline).

Subcommands:
  generate        -> synthesize a full map via the marked-point-process pipeline
                     (CLI-selectable overlays/renderers/stop point/vegetation sampler).
  render-vegetation -> run the pipeline through vegetation and save terrain-and-vegetation
                     PNGs for a few seeds, with either vegetation sampler.
  render-ontology -> render one sprite (+ passability mask overlay) per documented
                     ontology item — a documentation/debug tool, not part of the pipeline.
  mine-stats      -> mine every corpus statistic into data/pp/*.json.
  audit           -> report corpus objects the generator cannot reproduce, or print the
                     gameplay densities it draws from.
  extract-vmap    -> regenerate data/corpus/vmap/ from the .h3m corpus.
  corpus-match    -> compare generated gameplay placement to the corpus.
  render-sprites  -> render a .vmap with real H3 sprites, optionally beside a corpus map.
  regen-ontology  -> rebuild data/catalog/*.json from the editor's objects.txt.

`generate` and `render-vegetation` build and run a ``Pipeline`` (see
``core/pipeline.py``) from ``cli.steps.build_steps``; `render-ontology` stays outside that
model entirely — it renders the object taxonomy itself, never touches a generated map, and calls
``renderers.ontology_render`` directly.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.cli.audit import audit, densities
from vcmi_mapgen.cli.corpus_match import corpus_match
from vcmi_mapgen.cli.extract_vmap import extract_vmap
from vcmi_mapgen.cli.generate import (
    DEFAULT_OVERLAYS,
    DEFAULT_RENDERERS,
    OVERLAY_FACTORIES,
    RENDERER_CHOICES,
    GenerateOptions,
    VegetationRenderOptions,
    generate,
    render_vegetation,
)
from vcmi_mapgen.cli.mine_stats import MINERS, mine_stats
from vcmi_mapgen.cli.render_sprites import render_sprites
from vcmi_mapgen.cli.settings import Settings, load_settings, open_install
from vcmi_mapgen.cli.steps import DEFAULT_VEGETATION, GENERATE_STOP_POINTS, SAMPLERS
from vcmi_mapgen.renderers.ontology_render import render_ontology
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.catalog.regen import regenerate
from vcmi_mapgen.vcmi.catalog.tables import CLUSTERS
from vcmi_mapgen.vcmi.config import load_config
from vcmi_mapgen.vcmi.formats.lod import lod
from vcmi_mapgen.vcmi.install import VcmiInstall


@final
@dataclass
class Args(argparse.Namespace):
    func: Callable[[Args], None]
    out: str | None = None
    seed: int = 0
    size: int = 72
    no_water: bool = False
    players: int = 2
    teams: str = "ffa"
    water_mode: str | None = None
    subterrain: bool = False
    overlays: str = DEFAULT_OVERLAYS
    renderers: str = DEFAULT_RENDERERS
    stop_after: str | None = None
    only: list[str] | None = None
    seeds: Sequence[int] = ()
    vmap: str | None = None
    compare: str | None = None
    level: int | None = None
    densities: bool = False
    vegetation: str = DEFAULT_VEGETATION


def _open_catalog(settings: Settings) -> VcmiInstall:
    install = open_install(settings)
    ON.use_config(load_config(install))
    return install


def cmd_render_ontology(args: Args) -> None:
    settings = load_settings()
    install = _open_catalog(settings)
    render_ontology(lod(install.data_dir), args.out or str(settings.out_dir / "ontology"))


def cmd_mine_stats(args: Args) -> None:
    mine_stats(VcmiCatalog(), load_settings(), args.only or ())


def cmd_audit(args: Args) -> None:
    settings = load_settings()
    _ = _open_catalog(settings)
    catalog = VcmiCatalog()
    if args.densities:
        densities(catalog, settings.pp_dir, args.level or 0)
        return
    levels = [args.level] if args.level is not None else [0, 1]
    raise SystemExit(0 if audit(catalog, settings.pp_dir, levels) else 1)


def cmd_generate(args: Args) -> None:
    settings = load_settings()
    generate(
        _open_catalog(settings),
        settings,
        GenerateOptions(
            seed=args.seed,
            size=args.size,
            players=args.players,
            teams=args.teams,
            water_mode=args.water_mode or ("none" if args.no_water else "normal"),
            subterrain=args.subterrain,
            overlays=args.overlays,
            renderers=args.renderers,
            stop_after=args.stop_after,
            vegetation=args.vegetation,
        ),
    )


def cmd_render_vegetation(args: Args) -> None:
    settings = load_settings()
    render_vegetation(
        _open_catalog(settings),
        settings,
        VegetationRenderOptions(
            seeds=args.seeds,
            size=args.size,
            players=args.players,
            water_mode=args.water_mode or "normal",
            subterrain=args.subterrain,
            overlays=args.overlays,
            vegetation=args.vegetation,
        ),
    )


def cmd_extract_vmap(_args: Args) -> None:
    settings = load_settings()
    extract_vmap(load_config(open_install(settings)), settings.h3m_dir, settings.maps_dir)


def cmd_corpus_match(args: Args) -> None:
    settings = load_settings()
    _ = _open_catalog(settings)
    corpus_match(settings, args.seeds, args.size, args.subterrain)


def cmd_render_sprites(args: Args) -> None:
    settings = load_settings()
    install = _open_catalog(settings)
    if args.vmap is None:
        raise SystemExit("render-sprites needs a .vmap path")
    render_sprites(install, settings, args.vmap, args.compare, args.out)


def cmd_regen_ontology(_args: Args) -> None:
    install = open_install(load_settings())
    tree = regenerate(lod(install.data_dir), load_config(install))
    print("ontology taxonomy (regenerated)")
    for cluster in CLUSTERS:
        purposes = tree.get(cluster, {})
        types = sum(len(t) for t in purposes.values())
        leaves = sum(1 for x in ON.iter_leaves(tree) if x[0] == cluster)
        print(f"  {cluster:11s} purposes={len(purposes):2d} types={types:3d} leaves={leaves}")
    print(f"  total leaves: {sum(1 for _ in ON.iter_leaves(tree))}")


def _add_vegetation_arg(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--vegetation",
        choices=list(SAMPLERS),
        default=DEFAULT_VEGETATION,
        help="vegetation sampler: 'gibbs' (the marked point process) or 'field' (the cellular "
        + f"field) (default: {DEFAULT_VEGETATION})",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Learned procedural map generator for VCMI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pro = sub.add_parser(
        "render-ontology",
        help="render one sprite per documented ontology item to "
        + "out/ontology/<CLUSTER>/<terrain>/<type>.png",
    )
    _ = pro.add_argument("--out", default=None, help="output dir (default out/ontology)")
    _ = pro.set_defaults(func=cmd_render_ontology)

    pms = sub.add_parser("mine-stats", help="mine every corpus statistic into data/pp/*.json")
    _ = pms.add_argument(
        "--only",
        nargs="+",
        choices=list(MINERS),
        default=None,
        help="mine only the named statistics (default: all)",
    )
    _ = pms.set_defaults(func=cmd_mine_stats)

    pau = sub.add_parser(
        "audit",
        help="report corpus objects the generator cannot reproduce (empty = full variety "
        + "reachable), on both terrain levels unless --level is given",
    )
    _ = pau.add_argument("--level", type=int, default=None, help="0=surface, 1=underground")
    _ = pau.add_argument(
        "--densities",
        action="store_true",
        help="print the per-terrain gameplay densities instead of auditing",
    )
    _ = pau.set_defaults(func=cmd_audit)

    pev = sub.add_parser("extract-vmap", help="regenerate data/corpus/vmap/ from data/corpus/h3m/")
    _ = pev.set_defaults(func=cmd_extract_vmap)

    pcm = sub.add_parser("corpus-match", help="compare generated gameplay placement to the corpus")
    _ = pcm.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    _ = pcm.add_argument("--size", type=int, default=48)
    _ = pcm.add_argument("--subterrain", action="store_true")
    _ = pcm.set_defaults(func=cmd_corpus_match)

    prs = sub.add_parser(
        "render-sprites", help="render a .vmap with real H3 sprites to out/render/<name>_editor.png"
    )
    _ = prs.add_argument("vmap", nargs="?", default=None, help=".vmap path to render")
    _ = prs.add_argument("--compare", default=None, help="corpus map name to render alongside")
    _ = prs.add_argument("--out", default=None, help="output PNG path (default auto)")
    _ = prs.set_defaults(func=cmd_render_sprites)

    pro_regen = sub.add_parser(
        "regen-ontology", help="rebuild data/catalog/*.json from the editor's objects.txt"
    )
    _ = pro_regen.set_defaults(func=cmd_regen_ontology)

    pg = sub.add_parser(
        "generate", help="full map synthesized by the marked-point-process pipeline"
    )
    _ = pg.add_argument("--seed", type=int, default=0)
    _ = pg.add_argument("--size", type=int, default=72, help="W=H of the generated map")
    _ = pg.add_argument(
        "--no-water",
        action="store_true",
        dest="no_water",
        help="reassign water tiles to the nearest land terrain (land-only map)",
    )
    _ = pg.add_argument(
        "--players",
        type=int,
        default=2,
        help="number of players; the N largest zones get start towns",
    )
    _ = pg.add_argument(
        "--teams", default="ffa", help="team matrix: 'ffa', '2v2'-style, or explicit '0,0,1,1'"
    )
    _ = pg.add_argument(
        "--water-mode",
        choices=["none", "normal", "islands"],
        default=None,
        dest="water_mode",
        help="water style",
    )
    _ = pg.add_argument(
        "--subterrain",
        action="store_true",
        help="add a second, underground level connected to the surface by Subterranean Gate pairs",
    )
    _ = pg.add_argument(
        "--overlays",
        default=DEFAULT_OVERLAYS,
        help="comma-separated overlays to render on the PNG output "
        + f"(choices: {', '.join(OVERLAY_FACTORIES)}; 'none' to disable) "
        + f"(default: {DEFAULT_OVERLAYS})",
    )
    _ = pg.add_argument(
        "--renderers",
        default=DEFAULT_RENDERERS,
        help="comma-separated renderer(s) to run "
        + f"(choices: {', '.join(RENDERER_CHOICES)}) "
        + f"(default: {DEFAULT_RENDERERS})",
    )
    _ = pg.add_argument(
        "--stop-after",
        choices=GENERATE_STOP_POINTS,
        default=None,
        dest="stop_after",
        help="stop the pipeline early, right after the named step (debug), "
        + "instead of running the full pipeline through ScatterStep",
    )
    _add_vegetation_arg(pg)
    _ = pg.set_defaults(func=cmd_generate)

    prv = sub.add_parser(
        "render-vegetation",
        help="run the pipeline through vegetation and save terrain-and-vegetation PNGs to "
        + "out/render/vegetation/veg_s<seed>_<step>.png",
    )
    _ = prv.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    _ = prv.add_argument("--size", type=int, default=72, help="W=H of the generated map")
    _ = prv.add_argument("--players", type=int, default=2)
    _ = prv.add_argument(
        "--water-mode", choices=["none", "normal", "islands"], default=None, dest="water_mode"
    )
    _ = prv.add_argument("--subterrain", action="store_true")
    _ = prv.add_argument(
        "--overlays",
        default="none",
        help=f"comma-separated overlays (choices: {', '.join(OVERLAY_FACTORIES)}) "
        + "(default: none)",
    )
    _add_vegetation_arg(prv)
    _ = prv.set_defaults(func=cmd_render_vegetation)

    args = ap.parse_args(namespace=Args(func=cmd_render_ontology))
    args.func(args)


if __name__ == "__main__":
    main()
