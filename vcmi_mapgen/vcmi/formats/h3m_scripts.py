"""Skip the HotA 1.8 event-script section of an `.h3m` map (format HOTA9).

VCMI reads these scripts and discards them (`CMapLoaderH3M::readHotaScripts`). The map
generator has no use for them either, so this module only walks their bytes so the
sequential parser lands on the next section. Each action, condition and expression code
maps to a spec string whose letters name the values it holds, in order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, final


class ScriptReader(Protocol):
    """The primitive reads the script walker needs from the `.h3m` cursor."""

    def i8(self) -> int: ...

    def i16(self) -> int: ...

    def i32(self) -> int: ...

    def boolean(self) -> bool: ...

    def string(self) -> bytes: ...


class ScriptError(Exception):
    """Raised on a script code VCMI's reader does not know."""


ACTIONS: dict[int, str] = {
    2: "icee",
    3: "iBX",
    4: "B" + "e" * 7 + "b",
    5: "",
    6: "sa",
    7: "cssssab",
    8: "bieb",
    9: "biib",
    10: "ihhb",
    11: "snb",
    13: "caa",
    14: "ieib",
    15: "ib",
    16: "eb",
    17: "eib",
    18: "eib",
    19: "eib",
    20: "iib",
    21: "ib",
    22: "ib",
    23: "ei" * 7,
    24: "ii",
    25: "biib",
    26: "biib",
    27: "",
    28: "aeei",
    29: "sn",
}

CONDITIONS: dict[int, str] = {
    0: "b",
    1: "L",
    2: "L",
    3: "ee",
    4: "ee",
    5: "ee",
    6: "c",
    7: "ii",
    8: "ee",
    9: "ee",
    10: "ee",
    11: "i",
    12: "ii",
    14: "ii",
    15: "ii",
    16: "ii",
    17: "i",
    18: "ii",
    19: "i",
    20: "ii",
    21: "",
}

EXPRESSIONS: dict[int, str] = {
    0: "i",
    1: "i",
    2: "ie",
    3: "XX",
    4: "XX",
    5: "bi",
    6: "XX",
    7: "XX",
    8: "XX",
    9: "i",
    10: "",
    11: "i",
    12: "",
    13: "",
    14: "",
    15: "i",
    16: "ee",
    17: "ii",
}

SHOW_QUESTION = 12
CONDITIONAL_CHAIN = 1
EVENT_LISTS = 4
NEXT_IDS = 5
EVENT_MAPS = 5


@final
class HotaScripts:
    """Walks one map's script section on a shared cursor."""

    def __init__(self, reader: ScriptReader) -> None:
        self.r: ScriptReader = reader
        self._tokens: dict[str, Callable[[], object]] = {
            "s": reader.string,
            "b": reader.boolean,
            "B": reader.i8,
            "h": reader.i16,
            "i": reader.i32,
            "a": self.actions,
            "c": self.condition,
            "e": self.expression,
            "X": self.expression_body,
            "L": self._condition_list,
            "n": self._images,
        }

    def skip_section(self) -> None:
        """Walk the whole section: the active flag, then events, variables and maps."""
        r = self.r
        if not r.boolean():
            return
        for _ in range(EVENT_LISTS):
            for _ in range(r.i32()):
                self._run("ias")
        self._run("i" * NEXT_IDS)
        for _ in range(r.i32()):
            self._run("isbbi")
        for _ in range(EVENT_MAPS):
            for _ in range(r.i32()):
                _ = r.i32()

    def actions(self) -> None:
        r = self.r
        self._run("iB")
        for _ in range(r.i32()):
            code = r.i32()
            if code == SHOW_QUESTION:
                self._show_question()
            elif code == CONDITIONAL_CHAIN:
                self._conditional_chain()
            else:
                self._run(_spec(ACTIONS, code, "action"))

    def condition(self) -> None:
        _ = self.r.boolean()
        self.condition_body()

    def condition_body(self) -> None:
        self._run(_spec(CONDITIONS, self.r.i32(), "condition"))

    def expression(self) -> None:
        if self.r.boolean():
            self.expression_body()
        else:
            _ = self.r.i32()

    def expression_body(self) -> None:
        _ = self.r.boolean()
        self._run(_spec(EXPRESSIONS, self.r.i32(), "expression"))

    def _run(self, spec: str) -> None:
        for token in spec:
            _ = self._tokens[token]()

    def _condition_list(self) -> None:
        for _ in range(self.r.i32()):
            self.condition_body()

    def _images(self) -> None:
        for _ in range(self.r.i32()):
            self._run("iie")

    def _show_question(self) -> None:
        mode = self.r.i8()
        self._run("saa")
        if mode == 2:
            self.actions()
        count = self.r.i32() if mode in (0, 3) else 2
        for _ in range(count):
            self._run("iie")
        if mode in (1, 2):
            self._run("bi")

    def _conditional_chain(self) -> None:
        while True:
            self._run("cab")
            if self.r.i32() == 0:
                break
        _ = self.r.i32()


def _spec(table: dict[int, str], code: int, kind: str) -> str:
    spec = table.get(code)
    if spec is None:
        raise ScriptError(f"unknown HotA script {kind} code {code}")
    return spec
