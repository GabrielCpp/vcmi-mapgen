"""The corpus maps: `maps_vmap/<name>.vmap`, each loaded as a `MapState`."""

from __future__ import annotations

import os

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.vcmi.load import load_map


def corpus_path(name: str) -> str:
    return str(project_root() / "maps_vmap" / f"{name}.vmap")


def all_map_names() -> list[str]:
    d = project_root() / "maps_vmap"
    return [os.path.splitext(f)[0] for f in sorted(os.listdir(d)) if f.endswith(".vmap")]


def load_corpus_map(name: str) -> MapState:
    return load_map(corpus_path(name))


def corpus_maps() -> list[MapState]:
    maps: list[MapState] = []
    for name in all_map_names():
        try:
            maps.append(load_corpus_map(name))
        except Exception:
            continue
    return maps
