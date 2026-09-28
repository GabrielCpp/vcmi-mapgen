"""The corpus maps: `maps_vmap/<name>.vmap`, each loaded as a `MapState`."""

from __future__ import annotations

import os
from pathlib import Path

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.vcmi.load import load_map


def corpus_path(maps_dir: Path, name: str) -> str:
    return str(maps_dir / f"{name}.vmap")


def all_map_names(maps_dir: Path) -> list[str]:
    d = maps_dir
    return [os.path.splitext(f)[0] for f in sorted(os.listdir(d)) if f.endswith(".vmap")]


def load_corpus_map(maps_dir: Path, name: str) -> MapState:
    return load_map(corpus_path(maps_dir, name))


def corpus_maps(maps_dir: Path) -> list[MapState]:
    maps: list[MapState] = []
    for name in all_map_names(maps_dir):
        try:
            maps.append(load_corpus_map(maps_dir, name))
        except Exception:
            continue
    return maps
