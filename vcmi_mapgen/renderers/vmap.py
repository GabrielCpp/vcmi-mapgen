"""VmapRenderer — export a MapState as a playable VCMI .vmap file."""

from __future__ import annotations

import os

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.export import build_document
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.install import VcmiInstall
from vcmi_mapgen.vcmi.players import apply_playability, parse_teams

ROOT = project_root()


class VmapRenderer:
    """Export a MapState to a VCMI editor .vmap, then apply player slots and teams.

    Usage::

        renderer = VmapRenderer(out_dir="out/vmap")
        path = renderer.render(state, "mymap.vmap", name="My Map", teams_spec="ffa")
    """

    out_dir: str
    install: VcmiInstall | None

    def __init__(self, out_dir: str | None = None, install: VcmiInstall | None = None) -> None:
        self.out_dir = out_dir or str(ROOT / "out" / "vmap")
        self.install = install

    def render(
        self, state: MapState, path: str, name: str = "pp-map", teams_spec: str = "ffa"
    ) -> str:
        """Write a .vmap file. Returns the resolved path."""
        if not os.path.isabs(path):
            path = os.path.join(self.out_dir, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        doc = build_document(state, name, self.install)

        if state.player_towns:
            teams = parse_teams(teams_spec, len(state.player_towns))
            apply_playability(doc, state.player_towns, teams)
        return VM.write(doc, path)
