#!/usr/bin/env python3
import argparse
import ast
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

CONFIG = ".agent-checks.toml"
TABLE = "dead-code"
TEST_PATTERNS = ("*_test.py", "test_*.py", "conftest.py")
TEST_DIRS = frozenset({"tests", "test"})


def _root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip())


ROOT = _root()


@dataclass
class Module:
    name: str
    path: str
    is_test: bool
    imports: set[str] = field(default_factory=set)
    is_main: bool = False


def is_test_path(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in TEST_DIRS for part in pure.parts[:-1]):
        return True
    return any(fnmatch(pure.name, pattern) for pattern in TEST_PATTERNS)


def tracked_python() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        p
        for p in out.stdout.split("\0")
        if p and not _hidden(p) and (ROOT / p).is_file()
    ]


def _hidden(path: str) -> bool:
    return any(part.startswith(".") for part in PurePosixPath(path).parts)


def module_name(path: str, paths: set[str]) -> str | None:
    pure = PurePosixPath(path)
    parts = list(pure.with_suffix("").parts)
    start = len(parts) - 1
    while start > 0 and str(PurePosixPath(*parts[:start], "__init__.py")) in paths:
        start -= 1
    parts = parts[start:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    names = [node.test.left, *node.test.comparators]
    return any(isinstance(n, ast.Name) and n.id == "__name__" for n in names)


def _resolve_relative(module: Module, level: int, target: str | None) -> str:
    base = module.name.split(".")
    if not module.path.endswith("__init__.py"):
        base = base[:-1]
    base = base[: len(base) - (level - 1)] if level > 1 else base
    return ".".join([*base, target] if target else base)


def _dynamic_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute | ast.Name)
            and getattr(node.func, "attr", getattr(node.func, "id", "")) == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return found


def parse(module: Module) -> None:
    try:
        tree = ast.parse((ROOT / module.path).read_bytes(), filename=module.path)
    except SyntaxError:
        return
    module.is_main = module.path.endswith("__main__.py") or any(
        _is_main_guard(node) for node in tree.body
    )
    module.imports |= _dynamic_imports(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module.imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(module, node.level, node.module)
                if node.level
                else node.module or ""
            )
            module.imports.add(base)
            module.imports.update(f"{base}.{alias.name}" for alias in node.names)


def project_scripts() -> set[str]:
    try:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return set()
    project = data.get("project", {})
    targets = [*project.get("scripts", {}).values(), *project.get("gui-scripts", {}).values()]
    for group in project.get("entry-points", {}).values():
        targets.extend(group.values())
    return {target.split(":")[0].strip() for target in targets}


def configured_roots() -> list[str]:
    try:
        with (ROOT / CONFIG).open("rb") as handle:
            return list(tomllib.load(handle).get(TABLE, {}).get("roots", ()))
    except FileNotFoundError:
        return []


def expand(name: str, modules: dict[str, Module]) -> set[str]:
    parts = name.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1)} & modules.keys()


def reach(starts: set[str], modules: dict[str, Module]) -> set[str]:
    seen: set[str] = set()
    stack = [n for s in starts for n in expand(s, modules)]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for imported in modules[name].imports:
            stack.extend(expand(imported, modules) - seen)
    return seen


def line_count(path: str) -> int:
    return len((ROOT / path).read_bytes().splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Python modules no entry point reaches without going through a test."
    )
    parser.add_argument("--root", action="append", default=[], help="extra root module")
    parser.add_argument("--check", action="store_true", help="exit 1 when anything is unreachable")
    args = parser.parse_args()

    paths = tracked_python()
    path_set = set(paths)
    modules: dict[str, Module] = {}
    for path in paths:
        name = module_name(path, path_set)
        if name:
            modules[name] = Module(name, path, is_test_path(path))
    for module in modules.values():
        parse(module)

    production = {n: m for n, m in modules.items() if not m.is_test}
    explicit = project_scripts() | set(configured_roots()) | set(args.root)
    mains = {n for n, m in production.items() if m.is_main}
    reached = reach(explicit | mains, production)
    via_tests = reach({n for n, m in modules.items() if m.is_test}, modules)

    dead = sorted(n for n in production if n not in reached)
    print(f"roots: {len(explicit)} declared, {len(mains)} with a __main__ guard")
    for name in sorted(explicit | mains):
        print(f"  root {name}")
    if not dead:
        print("every production module is reachable from a root")
        return 0
    total = sum(line_count(production[n].path) for n in dead)
    print(f"unreachable: {len(dead)} modules, {total} lines")
    for name in dead:
        module = production[name]
        tag = "tests only" if name in via_tests else "nothing"
        print(f"  {module.path}  ({line_count(module.path)} lines, imported by {tag})")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
