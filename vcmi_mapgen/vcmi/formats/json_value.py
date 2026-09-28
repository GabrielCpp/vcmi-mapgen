from __future__ import annotations

import json
from typing import cast

from vcmi_mapgen.core.model import JsonValue


def loads(text: str) -> JsonValue:
    return cast("JsonValue", json.loads(text))


def as_object(value: JsonValue | None) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def as_list(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def as_str(value: JsonValue | None, default: str = "") -> str:
    return value if isinstance(value, str) else default


def as_int(value: JsonValue | None, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def opt_object(value: JsonValue | None) -> dict[str, JsonValue] | None:
    return value if isinstance(value, dict) else None


def opt_int(value: JsonValue | None) -> int | None:
    return value if isinstance(value, int) else None


def opt_bool(value: JsonValue | None) -> bool | None:
    return value if isinstance(value, bool) else None


def str_list(value: JsonValue | None) -> list[str]:
    return [item for item in as_list(value) if isinstance(item, str)]


def opt_str_list(value: JsonValue | None) -> list[str] | None:
    return str_list(value) if isinstance(value, list) else None
