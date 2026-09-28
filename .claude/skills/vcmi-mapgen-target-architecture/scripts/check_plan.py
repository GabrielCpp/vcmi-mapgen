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
DEFAULT_PLAN = "docs/architecture/plan.json"
DEFAULT_SOURCES = ("*.py", "*.ts", "*.tsx", "*.js", "*.go", "*.rs")
FATES = frozenset({"keep", "move", "split", "merge", "delete"})
SLICE_KEYS = ("id", "goal", "touches", "depends_on", "done_when", "rules")


def _root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip())


ROOT = _root()


@dataclass(frozen=True)
class Settings:
    plan: str
    sources: tuple[str, ...]
    exclude: tuple[str, ...]


def load_settings() -> Settings:
    try:
        with (ROOT / CONFIG).open("rb") as handle:
            table = tomllib.load(handle).get(TABLE, {})
    except FileNotFoundError:
        table = {}
    return Settings(
        plan=table.get("plan", DEFAULT_PLAN),
        sources=tuple(table.get("sources", DEFAULT_SOURCES)),
        exclude=tuple(table.get("exclude", ())),
    )


def tracked_sources(settings: Settings) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *settings.sources],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        p
        for p in out.stdout.split("\0")
        if p
        and (ROOT / p).is_file()
        and not any(part.startswith(".") for part in Path(p).parts)
        and not any(fnmatch(p, pattern) for pattern in settings.exclude)
    }


def check_fates(fates: object, sources: set[str], errors: list[str]) -> dict[str, dict]:
    if not isinstance(fates, dict):
        errors.append("fates must be an object keyed by current path")
        return {}
    for path, fate in fates.items():
        if not isinstance(fate, dict) or fate.get("fate") not in FATES:
            errors.append(f"fates[{path}]: fate must be one of {sorted(FATES)}")
            continue
        kind = fate["fate"]
        if kind in {"move", "split", "merge"} and not fate.get("to"):
            errors.append(f"fates[{path}]: {kind} needs 'to'")
        if kind != "keep" and not fate.get("slice"):
            errors.append(f"fates[{path}]: {kind} needs the 'slice' that performs it")
    for path in sorted(sources - fates.keys()):
        errors.append(f"no fate for tracked source {path}")
    for path in sorted(fates.keys() - sources):
        errors.append(f"fate for {path}, which is not a tracked source")
    return fates


def check_slices(slices: object, errors: list[str]) -> dict[str, dict]:
    if not isinstance(slices, list):
        errors.append("slices must be a list")
        return {}
    by_id: dict[str, dict] = {}
    for index, item in enumerate(slices):
        if not isinstance(item, dict):
            errors.append(f"slices[{index}] is not an object")
            continue
        missing = [key for key in SLICE_KEYS if key not in item]
        if missing:
            errors.append(f"slices[{index}] lacks {', '.join(missing)}")
            continue
        if item["id"] in by_id:
            errors.append(f"slice id {item['id']} appears twice")
        if not item["touches"]:
            errors.append(f"slice {item['id']} touches nothing")
        if not item["done_when"]:
            errors.append(f"slice {item['id']} has no done_when")
        by_id[item["id"]] = item
    for item in by_id.values():
        for dep in item["depends_on"]:
            if dep not in by_id:
                errors.append(f"slice {item['id']} depends on unknown slice {dep}")
    return by_id


def ancestors(by_id: dict[str, dict], errors: list[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def visit(slice_id: str) -> set[str]:
        if slice_id in result:
            return result[slice_id]
        if slice_id in visiting:
            errors.append(f"dependency cycle through slice {slice_id}")
            return set()
        visiting.add(slice_id)
        found: set[str] = set()
        for dep in by_id[slice_id]["depends_on"]:
            if dep in by_id:
                found |= {dep, *visit(dep)}
        visiting.discard(slice_id)
        result[slice_id] = found
        return found

    for slice_id in by_id:
        visit(slice_id)
    return result


def overlaps(a: str, b: str) -> bool:
    return fnmatch(a, b) or fnmatch(b, a) or a.startswith(b.rstrip("*")) or b.startswith(a.rstrip("*"))


def check_parallel(by_id: dict[str, dict], before: dict[str, set[str]], errors: list[str]) -> None:
    ids = sorted(by_id)
    for i, first in enumerate(ids):
        for second in ids[i + 1 :]:
            if first in before[second] or second in before[first]:
                continue
            shared = [
                (a, b)
                for a in by_id[first]["touches"]
                for b in by_id[second]["touches"]
                if overlaps(a, b)
            ]
            if shared:
                a, b = shared[0]
                errors.append(
                    f"slices {first} and {second} can run in parallel but both touch {a} / {b}"
                )


def check_fate_slices(fates: dict[str, dict], by_id: dict[str, dict], errors: list[str]) -> None:
    for path, fate in fates.items():
        slice_id = fate.get("slice")
        if not slice_id:
            continue
        item = by_id.get(slice_id)
        if item is None:
            errors.append(f"fates[{path}] names unknown slice {slice_id}")
        elif not any(fnmatch(path, t) or path.startswith(t.rstrip("*")) for t in item["touches"]):
            errors.append(f"fates[{path}] is done by slice {slice_id}, which does not touch it")


def waves(by_id: dict[str, dict], before: dict[str, set[str]]) -> list[list[str]]:
    depth = {sid: 0 for sid in by_id}
    for sid in sorted(by_id, key=lambda s: len(before[s])):
        depth[sid] = max((depth[d] + 1 for d in by_id[sid]["depends_on"] if d in by_id), default=0)
    out: list[list[str]] = [[] for _ in range(max(depth.values(), default=-1) + 1)]
    for sid, level in depth.items():
        out[level].append(sid)
    return [sorted(w) for w in out]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a target-architecture migration plan.")
    parser.add_argument("plan", nargs="?", help="plan path, default from .agent-checks.toml")
    parser.add_argument("--waves", action="store_true", help="print the parallel execution waves")
    args = parser.parse_args()

    settings = load_settings()
    plan_path = ROOT / (args.plan or settings.plan)
    try:
        plan = json.loads(plan_path.read_text())
    except FileNotFoundError:
        print(f"target-architecture: no plan at {plan_path.relative_to(ROOT)}")
        return 1
    except json.JSONDecodeError as error:
        print(f"target-architecture: {plan_path.relative_to(ROOT)} is not JSON: {error}")
        return 1

    errors: list[str] = []
    if plan.get("status") not in {"draft", "approved"}:
        errors.append("status must be 'draft' or 'approved'")
    fates = check_fates(plan.get("fates"), tracked_sources(settings), errors)
    by_id = check_slices(plan.get("slices"), errors)
    before = ancestors(by_id, errors)
    check_parallel(by_id, before, errors)
    check_fate_slices(fates, by_id, errors)

    for error in errors:
        print(f"target-architecture: {error}")
    if errors:
        print(f"target-architecture: {len(errors)} problems in {plan_path.relative_to(ROOT)}")
        return 1
    print(f"target-architecture: plan ok, {len(by_id)} slices, {len(fates)} fates, status {plan['status']}")
    if args.waves:
        for level, wave in enumerate(waves(by_id, before)):
            print(f"  wave {level}: {', '.join(wave)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
