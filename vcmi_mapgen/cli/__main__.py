"""Learned procedural map generator for VCMI (one CLI, one pipeline).

Subcommands:
  generate        -> synthesize a full map via the marked-point-process pipeline
                     (CLI-selectable overlays/renderers/stop point).
  render-ontology -> render one sprite (+ passability mask overlay) per documented
                     ontology item — a documentation/debug tool, not part of the pipeline.
  mine-stats      -> mine every corpus statistic into data/pp/*.json.
  extract-vmap    -> regenerate maps_vmap/ from the .h3m corpus.
  corpus-match    -> compare generated gameplay placement to the corpus.

`generate` builds and runs a ``Pipeline`` (see ``core/pipeline.py``) from
``cli.steps.build_steps``; `render-ontology` stays outside that model entirely — it
renders the object taxonomy itself, never touches a generated map, and calls
``renderers.ontology_render`` directly.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.cli.corpus_match import corpus_match
from vcmi_mapgen.cli.extract_vmap import extract_vmap
from vcmi_mapgen.cli.generate import (
    DEFAULT_OVERLAYS,
    DEFAULT_RENDERERS,
    OVERLAY_FACTORIES,
    RENDERER_CHOICES,
    GenerateOptions,
    generate,
)
from vcmi_mapgen.cli.steps import GENERATE_STOP_POINTS
from vcmi_mapgen.mine_stats import MINERS, mine_stats
from vcmi_mapgen.renderers.ontology_render import render_ontology


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


def cmd_render_ontology(args: Args) -> None:
    render_ontology(args.out)


def cmd_mine_stats(args: Args) -> None:
    mine_stats(args.only or ())


def cmd_generate(args: Args) -> None:
    generate(
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
        )
    )


def cmd_extract_vmap(_args: Args) -> None:
    extract_vmap()


def cmd_corpus_match(args: Args) -> None:
    corpus_match(args.seeds, args.size, args.subterrain)


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

    pev = sub.add_parser("extract-vmap", help="regenerate maps_vmap/ from the .h3m corpus in maps/")
    _ = pev.set_defaults(func=cmd_extract_vmap)

    pcm = sub.add_parser("corpus-match", help="compare generated gameplay placement to the corpus")
    _ = pcm.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    _ = pcm.add_argument("--size", type=int, default=48)
    _ = pcm.add_argument("--subterrain", action="store_true")
    _ = pcm.set_defaults(func=cmd_corpus_match)

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
    _ = pg.set_defaults(func=cmd_generate)

    args = ap.parse_args(namespace=Args(func=cmd_render_ontology))
    args.func(args)


if __name__ == "__main__":
    main()
