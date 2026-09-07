"""VmapRenderer — export a MapState as a playable VCMI .vmap file."""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

from vcmi_mapgen.models import MapState
from vcmi_mapgen.kit import vmap as VM
from vcmi_mapgen.kit.paths import project_root, vcmi_home

ROOT = project_root()


def _default_header() -> dict:
    """A real RMG-produced .vmap header if a local VCMI install has one (richer fidelity
    -- rumors, difficulty, description, ... -- preserved via VmapDocument.extra), else
    the static template."""
    rmg = glob.glob(os.path.join(vcmi_home(), "Maps", "RandomMaps", "*.vmap"))
    if rmg:
        return VM.read_header(rmg[0])
    tpl = str(ROOT / "data" / "vmap_header_template.json")
    return json.load(open(tpl))


class VmapRenderer:
    """Export a MapState to a VCMI editor .vmap, then apply player slots and teams.

    Usage::

        renderer = VmapRenderer(out_dir="out/vmap")
        path = renderer.render(state, "mymap.vmap", name="My Map", teams_spec="ffa")
    """

    def __init__(self, out_dir: str | None = None) -> None:
        self.out_dir = out_dir or str(ROOT / "out" / "vmap")

    def render(self, state: MapState, path: str, name: str = "pp-map",
               teams_spec: str = "ffa") -> str:
        """Write a .vmap file. Returns the resolved path."""
        if not os.path.isabs(path):
            path = os.path.join(self.out_dir, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        doc = self._build_document(state, name)

        if state.player_towns:
            teams = _parse_teams(teams_spec, len(state.player_towns))
            _apply_playability(doc, state.player_towns, teams)
        return VM.write(doc, path)

    def _build_document(self, state: MapState, name: str):
        """A finished MapState -> a full, writable VmapDocument: builds each object's
        VCMI-charset mask/visitableFrom, resolves `options["sameAsTown"]` markers
        ([x, y, l]) to the real town's instanceName, and gives every player slot a
        starting town in reading order (surface first) so the map opens playable even
        before `_apply_playability` runs its own, player-order-aware wiring.

        This computes straight from MapState -- no intermediate faithful-shaped dict:
        that shape existed for the (now-retired) identity-rebuild engine's corpus
        comparisons, which this renderer never needed (see vcmi_mapgen/AGENTS.md)."""
        levels = [state.cells[lvl] for lvl in sorted(state.cells)]
        terrain = [[[VM.tile_string(c) for c in row] for row in lvl] for lvl in levels]
        height, width = len(terrain[0]), len(terrain[0][0]) if terrain[0] else 0

        real_objs = [o for o in state.objs if o.get("type")]
        objects = []
        for o in real_objs:
            mask = VM.export_mask(o)
            vf = o.get("visitableFrom") or VM.visitable_from(o["mask"])
            objects.append(VM.VmapObject(
                instance_name="", type=o["type"], subtype=o["subtype"], l=o["l"],
                x=o["x"], y=o["y"], animation=o["animation"], mask=mask,
                visitable_from=vf, options=dict(o["options"]) if o.get("options") else None,
            ))
        for n, vo in enumerate(objects, 1):
            vo.instance_name = f"{vo.type}_{n}"

        # dwelling->town faction links: the generator marks `sameAsTown` with the town's
        # [x, y, l] (instance names are minted only here, above); VCMI wants the town's
        # instanceName. A marker whose town vanished is dropped (dwelling stays any-faction).
        town_names = {(vo.x, vo.y, vo.l): vo.instance_name
                      for vo in objects if vo.type in ("town", "randomTown")}
        for vo in objects:
            tag = (vo.options or {}).get("sameAsTown")
            if isinstance(tag, list):
                town_name = town_names.get(tuple(tag))
                if town_name:
                    vo.options["sameAsTown"] = town_name
                else:
                    del vo.options["sameAsTown"]
                    if not vo.options:
                        vo.options = None

        doc = VM.VmapDocument(
            name=name, width=width, height=height,
            two_level=len(terrain) > 1,
            terrain=terrain, objects=objects,
            **VM.header_fields(_default_header()),
        )
        # Deterministic regardless of the header source's own key order (a real RMG
        # header's dict order isn't guaranteed alphabetical -- see AGENTS.md's
        # determinism rule).
        doc.players.sort(key=lambda p: p.id)

        # Wire each player slot to its own starting town, surface towns first, then the
        # FIRST town encountered in state.objs put first (a stand-in "main town" when
        # `_apply_playability` doesn't run below, i.e. a neutral map with no
        # `player_towns`).
        town_objs = [o for o in real_objs if o.get("purpose") == "TOWN"]
        main = town_objs[0] if town_objs else None
        town_objs.sort(key=lambda o: (o.get("l", 0), o["y"], o["x"]))
        if main is not None:
            town_objs.sort(key=lambda o: o is not main)
        for i, pl in enumerate(doc.players):
            if i < len(town_objs):
                t = town_objs[i]
                pl.main_town = {"generateHero": True, "l": t.get("l", 0),
                                "x": t["x"] - 2, "y": t["y"] - 2}
                pl.can_play = "PlayerOrAI"
            else:
                pl.main_town = None
                pl.can_play = "false"
        return doc


def _parse_teams(spec: str, n: int) -> list[int]:
    """Team list from a spec string: 'ffa', '2v2', '1v3', or '0,0,1,1'."""
    if not spec or spec == "ffa":
        return list(range(n))
    if "v" in spec:
        sizes = [int(s) for s in spec.split("v")]
        if sum(sizes) != n:
            raise ValueError(f"teams {spec!r} sums to {sum(sizes)}, but players={n}")
        return [ti for ti, s in enumerate(sizes) for _ in range(s)]
    out = [int(s) for s in spec.split(",")]
    if len(out) != n:
        raise ValueError(f"teams {spec!r} lists {len(out)} ids, but players={n}")
    return out


def _apply_playability(doc, player_towns: list, teams: list[int]) -> None:
    """Deterministic playability overlay on a VmapDocument (in place):

      1. exactly len(player_towns) playable slots, slot i wired to its designated town
         (any faction allowed — the towns are usually randomTown) — AND the town OBJECT
         itself gets `options.owner = <player>` (the header's mainTown alone does NOT
         assign ownership; without the owner the town stays neutral),
      2. the team matrix (`teams[i]` = team id of player i; VCMI allies equal ids),
      3. victory = DEFEAT ALL (the canonical standardWin triggered event; standardDefeat =
         7 days without town), any special victory conditions stripped.
    """
    # doc.players is already sorted by color (fm_to_document's determinism guarantee).
    for i, pl in enumerate(doc.players):
        if i < len(player_towns):
            t = player_towns[i]
            pl.main_town = {"generateHero": True, "l": t.get("l", 0),
                            "x": t["x"] - 2, "y": t["y"] - 2}
            pl.can_play = "PlayerOrAI"
            pl.team = int(teams[i])
            if t.get("type") == "town":
                # concrete start town (spare-neutral top-up): the lobby must not offer
                # factions the map cannot honour — restrict to the authored one, exactly
                # like VCMI's own RMG maps do
                pl.allowed_factions = {"anyOf": [f"core:{t['subtype']}"]}
                pl.random_faction = None
            else:
                # randomTown start: any faction; VCMI resolves the OWNED random town to
                # the lobby pick (CGTownInstance::randomizeFaction). PlayerInfo::defaultCastle()
                # only returns RANDOM when isFactionRandom is set — an absent/permissive
                # allowedFactions alone still defaults the lobby dropdown to the first
                # faction (Castle) sorted by id. Field name from MapFormatJson.cpp's
                # serializePlayerInfo: handler.serializeBool("randomFaction", ...).
                pl.allowed_factions = None
                pl.random_faction = True
            for vo in doc.objects:                   # ownership lives on the town object
                if (vo.x == t["x"] and vo.y == t["y"] and vo.l == t.get("l", 0)
                        and vo.type in ("town", "randomTown")):
                    vo.options = dict(vo.options or {})
                    vo.options["owner"] = pl.id
                    break
        else:
            pl.main_town = None
            pl.can_play = "false"
            pl.team = None
    # VCMI's lobby/map-select screen reads alliances from this top-level grouping —
    # not from each player's individual "team" int above — so it must be set for
    # the UI to show teams at all. Real VCMI RMG maps omit the key entirely for FFA.
    groups = defaultdict(list)
    for i, pl in enumerate(doc.players[:len(player_towns)]):
        groups[int(teams[i])].append(pl.id)
    allied = [members for members in groups.values() if len(members) > 1]
    doc.teams = allied if allied else None

    MSG = {"exactStrings": None, "localStrings": None, "message": [2], "numbers": None}
    doc.triggered_events = {
        "standardVictory": {
            "condition": ["standardWin", {"type": "", "value": -1}],
            "effect": {"messageToSend": {"exactStrings": None, "localStrings": None,
                                         "message": None, "numbers": None,
                                         "stringsTextID": None}, "type": "victory"},
            "message": dict(MSG, stringsTextID=["core.genrltxt.659"])},
        "standardDefeat": {
            "condition": ["daysWithoutTown", {"type": "", "value": 7}],
            "effect": {"messageToSend": {"exactStrings": None, "localStrings": None,
                                         "message": None, "numbers": None,
                                         "stringsTextID": None}, "type": "defeat"},
            "message": dict(MSG, stringsTextID=["core.genrltxt.7"])}}
    doc.victory_icon_index = 11                       # "defeat all enemies"
    doc.victory_message = dict(MSG, stringsTextID=["core.vcdesc.0"])
    doc.defeat_icon_index = 3
    doc.defeat_message = dict(MSG, stringsTextID=["core.lcdesc.0"])
