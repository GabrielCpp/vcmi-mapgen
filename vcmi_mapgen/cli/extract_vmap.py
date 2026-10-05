"""Regenerate the corpus as real, editor-openable .vmap files.

Reads the committed .h3m corpus at <repo>/data/corpus/h3m/ and writes each one, via the h3m
parser + VCMI's own object-identity config, to <repo>/data/corpus/vmap/<name>.vmap — the
corpus's ONLY on-disk representation (replaces the old maps_json/ faithful-JSON
dialect; see the vmap-unification plan). Run:
`uv run python -m vcmi_mapgen.cli extract-vmap`.

Other folders of `.h3m` maps, HotA ones among them, convert the same way through
`--h3m-dir`, `--out-dir` and `--mods`. The enabled mods' map format renames each HotA
object and template to its VCMI identity and animation. A map of another format keeps the
base names.
"""

import os
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue, PlacedObject
from vcmi_mapgen.vcmi.config import VcmiConfig
from vcmi_mapgen.vcmi.content.map_format import NO_FORMAT, MapFormat
from vcmi_mapgen.vcmi.content.mods import NO_MODS, ModContent
from vcmi_mapgen.vcmi.footprint import footprint_of
from vcmi_mapgen.vcmi.formats import h3m
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats.vmap.document import PlayerSlot, VmapDocument, VmapObject
from vcmi_mapgen.vcmi.formats.vmap.mask import build_mask_from_h3m
from vcmi_mapgen.vcmi.formats.vmap.reader import header_template
from vcmi_mapgen.vcmi.formats.vmap.terrain import export_mask, visitable_from
from vcmi_mapgen.vcmi.formats.vmap.writer import write
from vcmi_mapgen.vcmi.tiles import Cell, tile_string


def _blank_players() -> list[PlayerSlot]:
    return [
        PlayerSlot(
            id=color, can_play=jv.as_str(jv.as_object(pl).get("canPlay"), "false"), main_town=None
        )
        for color, pl in jv.as_object(header_template()["players"]).items()
    ]


def convert(
    config: VcmiConfig, h3m_path: str, fmt: MapFormat = NO_FORMAT, mods: ModContent = NO_MODS
) -> tuple[VmapDocument, int, int]:
    """One `.h3m` map as a `.vmap` document, with its count of unresolved objects and of
    objects. ``config`` names each object, and ``fmt`` renames the objects and template
    animations of a HotA map. ``mods`` lists the mods its objects come from in the header."""
    m = h3m.parse_file(h3m_path)
    if m.fmt != h3m.HOTA:
        fmt = NO_FORMAT
    config = fmt.config(config)
    terrain = [
        [
            [
                tile_string(
                    Cell(
                        t=t.terrain,
                        view=t.view,
                        m=t.mirror & 3,
                        rt=t.river_type,
                        rd=t.river_dir,
                        ot=t.road_type,
                        od=t.road_dir,
                        rm=(t.mirror >> 2) & 3,
                        om=(t.mirror >> 4) & 3,
                    )
                )
                for t in row
            ]
            for row in lvl
        ]
        for lvl in m.terrain
    ]

    objects: list[VmapObject] = []
    unresolved = 0
    for n, o in enumerate(m.objects, 1):
        r = config.resolve(o.obj_class, o.obj_subclass)
        if not r:
            unresolved += 1
        vtype, sub = r if r else (None, None)
        tmpl = m.templates[o.template_index]
        anim = fmt.animation(o.animation)
        internal_mask = build_mask_from_h3m(tmpl.block_mask, tmpl.visit_mask)
        objects.append(
            VmapObject(
                instance_name=f"{vtype or 'unresolved'}_{n}",
                type=vtype,
                subtype=sub,
                level=o.level,
                x=o.x,
                y=o.y,
                animation=anim,
                mask=export_mask(
                    PlacedObject(
                        x=o.x,
                        y=o.y,
                        level=o.level,
                        purpose="",
                        kind=anim,
                        footprint=footprint_of(internal_mask),
                    )
                ),
                visitable_from=visitable_from(internal_mask),
            )
        )

    return (
        VmapDocument(
            name=m.name,
            width=m.width,
            height=m.height,
            two_level=m.two_level,
            terrain=terrain,
            objects=objects,
            players=_blank_players(),
            victory_icon_index=jv.opt_int(header_template()["victoryIconIndex"]),
            victory_message=jv.opt_object(header_template()["victoryMessage"]),
            defeat_icon_index=jv.opt_int(header_template()["defeatIconIndex"]),
            defeat_message=jv.opt_object(header_template()["defeatMessage"]),
            triggered_events=jv.opt_object(header_template()["triggeredEvents"]),
            extra=_extra(mods, objects),
        ),
        unresolved,
        len(objects),
    )


def _extra(mods: ModContent, objects: list[VmapObject]) -> dict[str, JsonValue]:
    extra: dict[str, JsonValue] = {
        "versionMajor": header_template()["versionMajor"],
        "versionMinor": header_template()["versionMinor"],
    }
    required = mods.requirement(o.animation for o in objects)
    if required:
        extra["mods"] = required
    return extra


def extract_vmap(
    config: VcmiConfig,
    h3m_dir: Path,
    out_dir: Path,
    fmt: MapFormat = NO_FORMAT,
    mods: ModContent = NO_MODS,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    maps = sorted(str(p) for p in h3m_dir.glob("*.h3m"))
    ok = 0
    total_obj = 0
    total_unresolved = 0
    for p in maps:
        try:
            doc, unresolved, n_obj = convert(config, p, fmt, mods)
        except Exception as e:
            print("PARSE FAIL", os.path.basename(p), e)
            continue
        _ = write(doc, str(out_dir / f"{os.path.basename(p)[:-4]}.vmap"))
        total_obj += n_obj
        total_unresolved += unresolved
        ok += 1
    print(
        f"extracted {ok}/{len(maps)} maps, {total_obj} objects, "
        + f"{total_unresolved} unresolved ({100 * total_unresolved / max(1, total_obj):.2f}%)"
    )
