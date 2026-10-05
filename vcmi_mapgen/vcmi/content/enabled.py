"""The content a map may use: the user's `ContentSetting` resolved into an `EnabledSet`."""

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.vcmi.content.manifest import ModManifest


class UnknownModError(ValueError):
    """A setting or a dependency names a mod that is not installed."""


class ContentConflictError(ValueError):
    """Two enabled mods declare that they cannot run together."""


@dataclass(frozen=True, slots=True)
class ContentSetting:
    """What the user asks for: whole mods by id, and object, creature, artifact or spell
    names to keep off the map. No mod means the base game with AB and SoD."""

    mods: frozenset[str] = frozenset()
    banned: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class EnabledSet:
    """The mods a map may draw from, closed over dependencies and submods, and the names it
    never draws."""

    mods: frozenset[str] = frozenset()
    banned: frozenset[str] = frozenset()

    def allows(self, *names: str | None) -> bool:
        return not any(n in self.banned for n in names if n is not None)


BASE_CONTENT = ContentSetting()
BASE_GAME = EnabledSet()


CORE_MOD = "vcmi"


def _required(roots: frozenset[str], manifests: Mapping[str, ModManifest]) -> set[str]:
    seen: set[str] = set()
    todo = sorted(roots)
    while todo:
        mod_id = todo.pop()
        if mod_id in seen or mod_id == CORE_MOD:
            continue
        if mod_id not in manifests:
            raise UnknownModError(f"mod {mod_id!r} is not installed")
        seen.add(mod_id)
        todo += sorted(manifests[mod_id].depends)
    return seen


def _joins(sub: ModManifest, mods: set[str]) -> bool:
    needs = sub.depends - {CORE_MOD}
    return not sub.keep_disabled and needs <= mods and not sub.conflicts & mods


def _with_submods(mods: set[str], manifests: Mapping[str, ModManifest]) -> frozenset[str]:
    grown = True
    while grown:
        subs = {s for m in sorted(mods) for s in manifests[m].submods if s not in mods}
        joining = {s for s in subs if _joins(manifests[s], mods)}
        mods |= joining
        grown = bool(joining)
    return frozenset(mods)


def enable(setting: ContentSetting, manifests: Mapping[str, ModManifest]) -> EnabledSet:
    """The setting's mods with every mod they depend on, then every submod whose own needs
    are met and that is not kept disabled. A missing dependency, or a conflict between the
    mods the setting requires, stops here."""
    required = _required(frozenset(m.lower() for m in setting.mods), manifests)
    for mod_id in sorted(required):
        clash = sorted(manifests[mod_id].conflicts & required)
        if clash:
            raise ContentConflictError(f"mod {mod_id!r} conflicts with {clash[0]!r}")
    return EnabledSet(_with_submods(required, manifests), setting.banned)
