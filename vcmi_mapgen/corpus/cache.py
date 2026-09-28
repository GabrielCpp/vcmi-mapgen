"""Read and write one corpus statistics cache file under ``data/pp/``."""

import json
from collections.abc import Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.vcmi.formats import json_value as jv

MINE_STATS = "uv run python -m vcmi_mapgen.cli mine-stats"
META_KEYS = frozenset({"_version", "_source"})


class MissingCacheError(FileNotFoundError):
    pass


def read(path: Path, version: int | None = None) -> dict[str, JsonValue]:
    if not path.exists():
        raise MissingCacheError(f"{path} is missing: run `{MINE_STATS}`")
    obj = jv.as_object(jv.loads(path.read_text()))
    if version is not None and obj.get("_version") != version:
        raise MissingCacheError(f"{path} is not at version {version}: run `{MINE_STATS}`")
    return obj


def write(path: Path, source: str, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps({"_source": source, **payload}))
