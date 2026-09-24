"""Regenerate the corpus as real, editor-openable .vmap files.

Reads the committed .h3m corpus at <repo>/maps/ and writes each one, via the h3m
parser + VCMI's own object-identity config, to <repo>/maps_vmap/<name>.vmap — the
corpus's ONLY on-disk representation (replaces the old maps_json/ faithful-JSON
dialect; see the vmap-unification plan). Run:
`uv run python -m vcmi_mapgen.extract_vmap`.
"""

import glob
import os
import re

from vcmi_mapgen import h3m
from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit import vcmi_config as vcmi_ids
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.kit.vmap.document import PlayerSlot, VmapDocument, VmapObject
from vcmi_mapgen.kit.vmap.mask import build_mask_from_h3m
from vcmi_mapgen.kit.vmap.terrain import export_mask, tile_string, visitable_from
from vcmi_mapgen.kit.vmap.writer import write
from vcmi_mapgen.models import Cell, PlacedObject

ROOT = project_root()
OUT = str(ROOT / "maps_vmap")
_HEADER_TEMPLATE = jv.as_object(jv.loads((ROOT / "data" / "vmap_header_template.json").read_text()))


def _blank_players() -> list[PlayerSlot]:
    return [
        PlayerSlot(
            id=color, can_play=jv.as_str(jv.as_object(pl).get("canPlay"), "false"), main_town=None
        )
        for color, pl in jv.as_object(_HEADER_TEMPLATE["players"]).items()
    ]


def convert(h3m_path: str) -> tuple[VmapDocument, int, int]:
    m = h3m.parse_file(h3m_path)
    terrain = [
        [
            [
                tile_string(
                    Cell(
                        t=t.terrain,
                        view=t.view,
                        m=t.mirror,
                        rt=t.river_type,
                        rd=t.river_dir,
                        ot=t.road_type,
                        od=t.road_dir,
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
        r = vcmi_ids.resolve(o.obj_class, o.obj_subclass)
        if not r:
            unresolved += 1
        vtype, sub = r if r else (None, None)
        tmpl = m.templates[o.template_index]
        anim = re.sub(r"\.(def|DEF)$", "", o.animation)
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
                        type=vtype,
                        subtype=sub,
                        animation=anim,
                        mask=tuple(internal_mask),
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
            victory_icon_index=jv.opt_int(_HEADER_TEMPLATE["victoryIconIndex"]),
            victory_message=jv.opt_object(_HEADER_TEMPLATE["victoryMessage"]),
            defeat_icon_index=jv.opt_int(_HEADER_TEMPLATE["defeatIconIndex"]),
            defeat_message=jv.opt_object(_HEADER_TEMPLATE["defeatMessage"]),
            triggered_events=jv.opt_object(_HEADER_TEMPLATE["triggeredEvents"]),
            extra={
                "versionMajor": _HEADER_TEMPLATE["versionMajor"],
                "versionMinor": _HEADER_TEMPLATE["versionMinor"],
            },
        ),
        unresolved,
        len(objects),
    )


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    maps = sorted(glob.glob(f"{ROOT}/maps/*.h3m"))
    ok = 0
    total_obj = 0
    total_unresolved = 0
    for p in maps:
        try:
            doc, unresolved, n_obj = convert(p)
        except Exception as e:
            print("PARSE FAIL", os.path.basename(p), e)
            continue
        _ = write(doc, f"{OUT}/{os.path.basename(p)[:-4]}.vmap")
        total_obj += n_obj
        total_unresolved += unresolved
        ok += 1
    print(
        f"extracted {ok}/{len(maps)} maps, {total_obj} objects, "
        + f"{total_unresolved} unresolved ({100 * total_unresolved / max(1, total_obj):.2f}%)"
    )


if __name__ == "__main__":
    main()
