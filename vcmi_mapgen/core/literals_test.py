"""Three checks an import contract cannot make, because they look at strings.

The core names no VCMI animation, no VCMI object type or option key, and no purpose outside
`core/model/purpose.py`. Each check reads the string literals of the core's non-test
modules."""

import ast
import io
import json
import re
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

from vcmi_mapgen.core.model.purpose import Purpose

_CORE = Path(__file__).parent
_TYPES_JSON = _CORE.parent / "vcmi" / "catalog" / "data" / "vcmi_types.json"
_PURPOSE_MODULE = _CORE / "model" / "purpose.py"
_ANIMATION = re.compile(r"av[a-z0-9]+", re.IGNORECASE)
_OPTION_KEYS = frozenset(
    {
        "allOf",
        "anyOf",
        "artifacts",
        "character",
        "completedText",
        "creatures",
        "creaturesChange",
        "firstVisitText",
        "generateHero",
        "guardMessage",
        "heroExperience",
        "heroLevel",
        "limiter",
        "localStrings",
        "manaPercentage",
        "messageToSend",
        "movePercentage",
        "movePoints",
        "nextVisitText",
        "noneOf",
        "possibleSpells",
        "rewardable",
        "sameAsTown",
        "selectMode",
        "spellCast",
        "stringsTextID",
        "visitMode",
    }
)
"""Hardcoded, not read from VCMI: the option keys `vcmi/options.py` writes, minus the
generic words such as `type` and `value` that the core uses for its own meaning."""


def _literals(path: Path) -> Iterator[tuple[int, str]]:
    for tok in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
        if tok.type == tokenize.STRING:
            value = cast("object", ast.literal_eval(tok.string))
            if isinstance(value, str):
                yield tok.start[0], value


def _hits(flag: Callable[[Path, str], bool]) -> list[str]:
    return [
        f"{path.relative_to(_CORE)}:{line}: {value!r}"
        for path in sorted(_CORE.rglob("*.py"))
        if not path.name.endswith("_test.py")
        for line, value in _literals(path)
        if flag(path, value)
    ]


def test_core_names_no_animation() -> None:
    assert _hits(lambda _p, v: _ANIMATION.fullmatch(v) is not None) == []


def test_core_names_no_vcmi_type_or_option_key() -> None:
    types = frozenset(cast("dict[str, object]", json.loads(_TYPES_JSON.read_text())))
    assert _hits(lambda _p, v: v in types or v in _OPTION_KEYS) == []


def test_core_names_purposes_only_in_purpose_module() -> None:
    purposes = frozenset(p.value for p in Purpose)
    assert _hits(lambda p, v: v in purposes and p != _PURPOSE_MODULE) == []
