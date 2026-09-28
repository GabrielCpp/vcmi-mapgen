#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "target-architecture"
DEFAULT_PLAN_PATH = "docs/architecture/plan.json"
DEFAULT_SOURCES = ("*.py", "*.ts", "*.tsx", "*.js", "*.go", "*.rs")
FATES = frozenset({"keep", "move", "split", "merge", "delete"})
SLICE_KEYS = ("id", "goal", "touches", "depends_on", "done_when", "rules")
STATUSES = frozenset({"draft", "approved"})


def _repo_root() -> Path:
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(toplevel.stdout.strip())


REPO_ROOT = _repo_root()


class ConfigError(ValueError):
    """A value in the config table has the wrong type."""


@dataclass(frozen=True)
class Settings:
    plan_path: str
    sources: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class Fate:
    kind: str
    to: str
    slice_id: str


@dataclass(frozen=True)
class Slice:
    id: str
    goal: str
    touches: tuple[str, ...]
    depends_on: tuple[str, ...]
    done_when: tuple[str, ...]
    rules: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    status: str
    fated_paths: frozenset[str]
    fates: dict[str, Fate]
    slices: dict[str, Slice]


def _string_list_or_none(value: object) -> tuple[str, ...] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(item for item in value if isinstance(item, str))
    return None


def _config_strings(table: dict[str, object], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if key not in table:
        return default
    value = _string_list_or_none(table[key])
    if value is None:
        raise ConfigError(f"{CONFIG} [{TABLE}] {key} must be a list of strings")
    return value


def load_settings() -> Settings:
    try:
        with (REPO_ROOT / CONFIG).open("rb") as handle:
            loaded = tomllib.load(handle).get(TABLE, {})
    except FileNotFoundError:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"{CONFIG} [{TABLE}] must be a table")
    table: dict[str, object] = {str(key): value for key, value in loaded.items()}
    plan_path = table.get("plan", DEFAULT_PLAN_PATH)
    if not isinstance(plan_path, str):
        raise ConfigError(f"{CONFIG} [{TABLE}] plan must be a string")
    return Settings(
        plan_path=plan_path,
        sources=_config_strings(table, "sources", DEFAULT_SOURCES),
        exclude=_config_strings(table, "exclude", ()),
    )


def tracked_sources(settings: Settings) -> set[str]:
    ls_files = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--cached", "--", *settings.sources],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        p
        for p in ls_files.stdout.split("\0")
        if p
        and (REPO_ROOT / p).is_file()
        and not any(part.startswith(".") for part in Path(p).parts)
        and not any(fnmatch(p, pattern) for pattern in settings.exclude)
    }


def _string_or_empty_when_absent(entry: dict[str, object], key: str) -> str:
    """The string at *key*, or "" when the key is absent. A value that is not a string raises TypeError."""
    value = entry.get(key, "")
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value


def parse_fate(path: str, raw: object, errors: list[str]) -> Fate | None:
    if not isinstance(raw, dict):
        errors.append(f"fates[{path}] is not an object")
        return None
    entry: dict[str, object] = {str(key): value for key, value in raw.items()}
    kind = entry.get("fate")
    if not isinstance(kind, str) or kind not in FATES:
        errors.append(f"fates[{path}]: fate must be one of {sorted(FATES)}")
        return None
    try:
        to = _string_or_empty_when_absent(entry, "to")
        slice_id = _string_or_empty_when_absent(entry, "slice")
    except TypeError:
        errors.append(f"fates[{path}]: 'to' and 'slice' must be strings")
        return None
    if kind in {"move", "split", "merge"} and not to:
        errors.append(f"fates[{path}]: {kind} needs 'to'")
    if kind != "keep" and not slice_id:
        errors.append(f"fates[{path}]: {kind} needs the 'slice' that performs it")
    return Fate(kind=kind, to=to, slice_id=slice_id)


def parse_fates(raw: object, errors: list[str]) -> tuple[frozenset[str], dict[str, Fate]]:
    if not isinstance(raw, dict):
        errors.append("fates must be an object keyed by current path")
        return frozenset(), {}
    fates: dict[str, Fate] = {}
    for path, entry in raw.items():
        fate = parse_fate(str(path), entry, errors)
        if fate is not None:
            fates[str(path)] = fate
    return frozenset(str(path) for path in raw), fates


def _done_when_commands_or_none(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,) if value else ()
    return _string_list_or_none(value)


def parse_slice(index: int, raw: object, errors: list[str]) -> Slice | None:
    if not isinstance(raw, dict):
        errors.append(f"slices[{index}] is not an object")
        return None
    entry: dict[str, object] = {str(key): value for key, value in raw.items()}
    missing = [key for key in SLICE_KEYS if key not in entry]
    if missing:
        errors.append(f"slices[{index}] lacks {', '.join(missing)}")
        return None
    slice_id, goal = entry["id"], entry["goal"]
    touches, depends_on = _string_list_or_none(entry["touches"]), _string_list_or_none(entry["depends_on"])
    done_when, rules = _done_when_commands_or_none(entry["done_when"]), _string_list_or_none(entry["rules"])
    if not isinstance(slice_id, str) or not isinstance(goal, str):
        errors.append(f"slices[{index}]: id and goal must be strings")
        return None
    if touches is None or depends_on is None or rules is None:
        errors.append(f"slice {slice_id}: touches, depends_on and rules must be lists of strings")
        return None
    if done_when is None:
        errors.append(f"slice {slice_id}: done_when must be a string or a list of strings")
        return None
    if not touches:
        errors.append(f"slice {slice_id} touches nothing")
    if not done_when:
        errors.append(f"slice {slice_id} has no done_when")
    return Slice(id=slice_id, goal=goal, touches=touches, depends_on=depends_on, done_when=done_when, rules=rules)


def parse_slices(raw: object, errors: list[str]) -> dict[str, Slice]:
    if not isinstance(raw, list):
        errors.append("slices must be a list")
        return {}
    by_id: dict[str, Slice] = {}
    for index, entry in enumerate(raw):
        parsed = parse_slice(index, entry, errors)
        if parsed is None:
            continue
        if parsed.id in by_id:
            errors.append(f"slice id {parsed.id} appears twice")
        by_id[parsed.id] = parsed
    for item in by_id.values():
        for dep in item.depends_on:
            if dep not in by_id:
                errors.append(f"slice {item.id} depends on unknown slice {dep}")
    return by_id


def parse_plan(raw: object, errors: list[str]) -> Plan:
    if not isinstance(raw, dict):
        errors.append("the plan must be a JSON object")
        return Plan(status="", fated_paths=frozenset(), fates={}, slices={})
    document: dict[str, object] = {str(key): value for key, value in raw.items()}
    status = document.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("status must be 'draft' or 'approved'")
        status = ""
    fated_paths, fates = parse_fates(document.get("fates"), errors)
    return Plan(status=status, fated_paths=fated_paths, fates=fates, slices=parse_slices(document.get("slices"), errors))


def check_fate_coverage(plan: Plan, sources: set[str], errors: list[str]) -> None:
    for path in sorted(sources - plan.fated_paths):
        errors.append(f"no fate for tracked source {path}")
    for path in sorted(plan.fated_paths - sources):
        errors.append(f"fate for {path}, which is not a tracked source")


def slices_on_or_behind_a_cycle(by_id: dict[str, Slice]) -> list[str]:
    """The slices on a dependency cycle or depending on one, sorted. Empty when the graph is acyclic."""
    remaining = {sid: {d for d in item.depends_on if d in by_id} for sid, item in by_id.items()}
    while True:
        ready = {sid for sid, deps in remaining.items() if not deps}
        if not ready:
            return sorted(remaining)
        for sid in ready:
            del remaining[sid]
        for deps in remaining.values():
            deps -= ready


def ancestors_by_slice(by_id: dict[str, Slice]) -> dict[str, set[str]]:
    """Every slice's transitive dependencies. The graph must be acyclic."""
    result: dict[str, set[str]] = {}

    def visit(slice_id: str) -> set[str]:
        if slice_id not in result:
            found: set[str] = set()
            for dep in by_id[slice_id].depends_on:
                if dep in by_id:
                    found |= {dep, *visit(dep)}
            result[slice_id] = found
        return result[slice_id]

    for slice_id in by_id:
        _ = visit(slice_id)
    return result


def overlaps(a: str, b: str) -> bool:
    return fnmatch(a, b) or fnmatch(b, a) or a.startswith(b.rstrip("*")) or b.startswith(a.rstrip("*"))


def check_parallel_slices_touch_disjoint_paths(by_id: dict[str, Slice], ancestry: dict[str, set[str]], errors: list[str]) -> None:
    ids = sorted(by_id)
    for i, first in enumerate(ids):
        for second in ids[i + 1 :]:
            if first in ancestry[second] or second in ancestry[first]:
                continue
            shared = [
                (a, b)
                for a in by_id[first].touches
                for b in by_id[second].touches
                if overlaps(a, b)
            ]
            if shared:
                a, b = shared[0]
                errors.append(
                    f"slices {first} and {second} can run in parallel but both touch {a} / {b}"
                )


def check_each_fate_slice_exists_and_touches_its_path(fates: dict[str, Fate], by_id: dict[str, Slice], errors: list[str]) -> None:
    for path, fate in fates.items():
        if not fate.slice_id:
            continue
        item = by_id.get(fate.slice_id)
        if item is None:
            errors.append(f"fates[{path}] names unknown slice {fate.slice_id}")
        elif not any(fnmatch(path, t) or path.startswith(t.rstrip("*")) for t in item.touches):
            errors.append(f"fates[{path}] is done by slice {fate.slice_id}, which does not touch it")


def waves(by_id: dict[str, Slice], ancestry: dict[str, set[str]]) -> list[list[str]]:
    depth = {sid: 0 for sid in by_id}
    for sid in sorted(by_id, key=lambda s: len(ancestry[s])):
        depth[sid] = max((depth[d] + 1 for d in by_id[sid].depends_on if d in by_id), default=0)
    slice_ids_by_wave: list[list[str]] = [[] for _ in range(max(depth.values(), default=-1) + 1)]
    for sid, level in depth.items():
        slice_ids_by_wave[level].append(sid)
    return [sorted(w) for w in slice_ids_by_wave]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a target-architecture migration plan.")
    _ = parser.add_argument("plan", nargs="?", help="plan path, default from .agent-checks.toml")
    _ = parser.add_argument("--waves", action="store_true", help="print the parallel execution waves")
    args = parser.parse_args()
    plan_arg: str | None = args.plan
    show_waves: bool = args.waves

    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"target-architecture: {error}")
        return 1
    plan_path = REPO_ROOT / (plan_arg or settings.plan_path)
    try:
        raw: object = json.loads(plan_path.read_text())
    except FileNotFoundError:
        print(f"target-architecture: no plan at {plan_path.relative_to(REPO_ROOT)}")
        return 1
    except json.JSONDecodeError as error:
        print(f"target-architecture: {plan_path.relative_to(REPO_ROOT)} is not JSON: {error}")
        return 1

    errors: list[str] = []
    plan = parse_plan(raw, errors)
    check_fate_coverage(plan, tracked_sources(settings), errors)
    check_each_fate_slice_exists_and_touches_its_path(plan.fates, plan.slices, errors)
    slices_blocked_by_cycle = slices_on_or_behind_a_cycle(plan.slices)
    if slices_blocked_by_cycle:
        errors.append(f"dependency cycle among or behind slices {', '.join(slices_blocked_by_cycle)}")
        ancestry: dict[str, set[str]] = {}
    else:
        ancestry = ancestors_by_slice(plan.slices)
        check_parallel_slices_touch_disjoint_paths(plan.slices, ancestry, errors)

    for error in errors:
        print(f"target-architecture: {error}")
    if errors:
        print(f"target-architecture: {len(errors)} problems in {plan_path.relative_to(REPO_ROOT)}")
        return 1
    print(f"target-architecture: plan ok, {len(plan.slices)} slices, {len(plan.fates)} fates, status {plan.status}")
    if show_waves:
        for level, wave in enumerate(waves(plan.slices, ancestry)):
            print(f"  wave {level}: {', '.join(wave)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
