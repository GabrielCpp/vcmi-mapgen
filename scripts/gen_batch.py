import argparse
import os
import random
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SIZES = [36, 72, 108, 144]
COUNT = 100
WORKERS = max(1, (os.cpu_count() or 2) // 2)
INT64_MAX = 2**63 - 1
OUT_DIR = Path(__file__).resolve().parent.parent / "out"
VCMI_DIR = Path.home() / ".local" / "share" / "vcmi" / "Maps" / "VcmiMapsGen"


def generate(seed: int, vcmi_dir: Path | None) -> tuple[int, int, int]:
    size = SIZES[seed % len(SIZES)]
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "vcmi_mapgen.cli",
        "generate",
        "--seed",
        str(seed),
        "--size",
        str(size),
        "--players",
        "4",
        "--teams",
        "2v2",
        "--no-water",
        "--subterrain",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"seed {seed} size {size} failed:\n{result.stderr[-2000:]}", file=sys.stderr)
    elif vcmi_dir is not None:
        stem = f"ppmap_s{seed}_{size}"
        _ = shutil.copy2(OUT_DIR / stem / f"{stem}.vmap", vcmi_dir / f"{stem}.vmap")
    return seed, size, result.returncode


def find_seed(seeds: set[int]) -> int:
    seed = random.randint(1, INT64_MAX)
    while seed in seeds:
        seed = random.randint(1, INT64_MAX)
    seeds.add(seed)
    return seed


class Args(argparse.Namespace):
    count: int = COUNT
    dest: str = "out"
    vcmi_dir: Path = VCMI_DIR


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="generate a batch of random-seed maps")
    _ = parser.add_argument(
        "--count", type=int, default=COUNT, help=f"maps to generate (default {COUNT})"
    )
    _ = parser.add_argument(
        "--dest",
        choices=["out", "vcmi"],
        default="out",
        help="'out' keeps each map's folder in out/; 'vcmi' also copies each .vmap to --vcmi-dir",
    )
    _ = parser.add_argument(
        "--vcmi-dir",
        type=Path,
        default=VCMI_DIR,
        help=f"VCMI maps folder for --dest vcmi (default {VCMI_DIR})",
    )
    return parser.parse_args(namespace=Args())


def main() -> None:
    args = parse_args()
    count = args.count
    vcmi_dir = args.vcmi_dir if args.dest == "vcmi" else None
    if vcmi_dir is not None:
        vcmi_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    seeds: set[int] = set()

    with ThreadPoolExecutor(WORKERS) as pool:
        # pick seeds up front (find_seed mutates `seeds`, so keep it single-threaded)
        chosen = [find_seed(seeds) for _ in range(count)]
        futures = {pool.submit(generate, seed, vcmi_dir): seed for seed in chosen}

        for fut in as_completed(futures):
            seed = futures[fut]
            _, size, code = fut.result()
            failed += code != 0
            print(f"seed {seed:3d} size {size:3d} {'ok' if code == 0 else 'FAILED'}", flush=True)
    where = f"out/ and {vcmi_dir}" if vcmi_dir is not None else "out/"
    print(f"{count - failed}/{count} maps in {where}")


if __name__ == "__main__":
    main()
