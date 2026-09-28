"""MapState to VmapDocument: the one translation from a finished map to a writable .vmap."""

from __future__ import annotations

from vcmi_mapgen.core.model import JsonValue, MapState
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.footprint import mask_rows
from vcmi_mapgen.vcmi.formats import json_value as jv
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.install import VcmiInstall
from vcmi_mapgen.vcmi.options import options_of
from vcmi_mapgen.vcmi.players import main_town
from vcmi_mapgen.vcmi.tiles import TilerTables, tile_strings

ROOT = project_root()
ALL_SIDES: tuple[str, ...] = ("+++", "+-+", "+++")


def _default_header(install: VcmiInstall | None) -> dict[str, JsonValue]:
    """A real RMG-produced .vmap header if a local VCMI install has one (richer fidelity
    -- rumors, difficulty, description, ... -- preserved via VmapDocument.extra), else
    the static template."""
    rmg = list((install.home / "Maps" / "RandomMaps").glob("*.vmap")) if install else []
    if rmg:
        return VM.read_header(str(rmg[0]))
    tpl = ROOT / "data" / "vmap_header_template.json"
    return jv.as_object(jv.loads(tpl.read_text()))


def build_document(
    state: MapState, name: str, install: VcmiInstall | None, tables: TilerTables
) -> VM.VmapDocument:
    """A finished MapState -> a full, writable VmapDocument: tiles each level's terrain
    with ``tables``, derives each object's VCMI
    type and subtype from its kind, turns its payload into VCMI options, builds its
    VCMI-charset mask/visitableFrom (a borderGate opens from every side), resolves
    `options["sameAsTown"]` markers
    ([x, y, l]) to the real town's instanceName, and gives every player slot a
    starting town in reading order (surface first) so the map opens playable even
    before `players.apply_playability` runs its own, player-order-aware wiring.

    This computes straight from MapState -- no intermediate faithful-shaped dict:
    that shape existed for the (now-retired) identity-rebuild engine's corpus
    comparisons, which this export never needed (see vcmi_mapgen/AGENTS.md)."""
    terrain = [tile_strings(state.terrain[lvl], tables) for lvl in sorted(state.terrain)]
    height, width = len(terrain[0]), len(terrain[0][0]) if terrain[0] else 0

    typed = [(o, OB.identity_of(o.kind)) for o in state.objs]
    real = [(o, ident) for o, ident in typed if ident.type]
    real_objs = [o for o, _ident in real]
    objects: list[VM.VmapObject] = []
    for o, ident in real:
        mask = VM.export_mask(o)
        vf = (
            list(ALL_SIDES)
            if ident.type == "borderGate"
            else VM.visitable_from(mask_rows(o.footprint))
        )
        objects.append(
            VM.VmapObject(
                instance_name="",
                type=ident.type or "",
                subtype=ident.subtype,
                level=o.level,
                x=o.x,
                y=o.y,
                animation=o.kind,
                mask=mask,
                visitable_from=vf,
                options=options_of(o.payload),
            )
        )
    for n, vo in enumerate(objects, 1):
        vo.instance_name = f"{vo.type}_{n}"

    # dwelling->town faction links: the generator marks `sameAsTown` with the town's
    # [x, y, l] (instance names are minted only here, above); VCMI wants the town's
    # instanceName. A marker whose town vanished is dropped (dwelling stays any-faction).
    town_names: dict[tuple[JsonValue, ...], str] = {
        (vo.x, vo.y, vo.level): vo.instance_name
        for vo in objects
        if vo.type in ("town", "randomTown")
    }
    for vo in objects:
        opts = vo.options
        tag = opts.get("sameAsTown") if opts else None
        if opts is not None and isinstance(tag, list):
            town_name = town_names.get(tuple(tag))
            if town_name:
                opts["sameAsTown"] = town_name
            else:
                del opts["sameAsTown"]
                if not opts:
                    vo.options = None

    doc = VM.VmapDocument(
        name=name,
        width=width,
        height=height,
        two_level=len(terrain) > 1,
        terrain=terrain,
        objects=objects,
        **VM.header_fields(_default_header(install)),
    )
    # Deterministic regardless of the header source's own key order (a real RMG
    # header's dict order isn't guaranteed alphabetical -- see AGENTS.md's
    # determinism rule).
    doc.players.sort(key=lambda p: p.id)

    # Wire each player slot to its own starting town, surface towns first, then the
    # FIRST town encountered in state.objs put first (a stand-in "main town" when
    # `players.apply_playability` doesn't run below, i.e. a neutral map with no
    # `player_towns`).
    town_objs = [o for o in real_objs if o.purpose == "TOWN"]
    main = town_objs[0] if town_objs else None
    town_objs.sort(key=lambda o: (o.level, o.y, o.x))
    if main is not None:
        town_objs.sort(key=lambda o: o is not main)
    for i, pl in enumerate(doc.players):
        if i < len(town_objs):
            t = town_objs[i]
            pl.main_town = main_town(t)
            pl.can_play = "PlayerOrAI"
        else:
            pl.main_town = None
            pl.can_play = "false"
    return doc
