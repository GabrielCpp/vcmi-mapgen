"""The corpus maps: `data/corpus/vmap/<name>.vmap`, each loaded as a `MapState`."""

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


def named_corpus_maps(maps_dir: Path) -> list[tuple[str, MapState]]:
    maps: list[tuple[str, MapState]] = []
    for name in all_map_names(maps_dir):
        try:
            maps.append((name, load_corpus_map(maps_dir, name)))
        except Exception:
            continue
    return maps


def corpus_maps(maps_dir: Path) -> list[MapState]:
    return [m for _, m in named_corpus_maps(maps_dir)]
