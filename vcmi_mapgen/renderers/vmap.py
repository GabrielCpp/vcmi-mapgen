"""VmapRenderer — export a MapState as a playable VCMI .vmap file."""

from __future__ import annotations

import os

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.vcmi.content.mods import NO_MODS, ModContent
from vcmi_mapgen.vcmi.export import build_document
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.install import VcmiInstall
from vcmi_mapgen.vcmi.players import apply_playability, parse_teams
from vcmi_mapgen.vcmi.tiles import TilerTables


class VmapRenderer:
    """Export a MapState to a VCMI editor .vmap, then apply player slots and teams. The
    tile art comes from ``tables``, the corpus tiler the caller loaded, and ``mods`` holds
    the enabled mods the map's objects may come from.

    Usage::

        renderer = VmapRenderer("out/vmap", tables)
        path = renderer.render(state, "mymap.vmap", name="My Map", teams_spec="ffa")
    """

    out_dir: str
    install: VcmiInstall | None
    tables: TilerTables
    mods: ModContent

    def __init__(
        self,
        out_dir: str,
        tables: TilerTables,
        install: VcmiInstall | None = None,
        mods: ModContent = NO_MODS,
    ) -> None:
        self.out_dir = out_dir
        self.install = install
        self.tables = tables
        self.mods = mods

    def render(
        self, state: MapState, path: str, name: str = "pp-map", teams_spec: str = "ffa"
    ) -> str:
        """Write a .vmap file. Returns the resolved path."""
        if not os.path.isabs(path):
            path = os.path.join(self.out_dir, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        doc = build_document(state, name, self.install, self.tables, self.mods)

        if state.player_towns:
            teams = parse_teams(teams_spec, len(state.player_towns))
            apply_playability(doc, state.player_towns, teams)
        return VM.write(doc, path)
