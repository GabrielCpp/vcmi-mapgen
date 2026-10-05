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


def as_float(value: JsonValue | None, default: float = 0.0) -> float:
    return float(value) if isinstance(value, int | float) else default


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


def _uncommented(text: str) -> str:
    out: list[str] = []
    comma = -1
    i, n, quoted = 0, len(text), False
    while i < n:
        c = text[i]
        if quoted:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                quoted = False
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        elif c in "}]" and comma >= 0 and not "".join(out[comma + 1 :]).strip():
            del out[comma]
            out.append(c)
            comma = -1
        else:
            out.append(c)
            quoted = c == '"'
            comma = len(out) - 1 if c == "," else comma if c.isspace() else -1
        i += 1
    return "".join(out)


def loads_relaxed(text: str) -> JsonValue:
    """Parse VCMI's relaxed JSON: comments outside strings, trailing commas and raw control
    characters inside strings."""
    return cast("JsonValue", json.loads(_uncommented(text), strict=False))
