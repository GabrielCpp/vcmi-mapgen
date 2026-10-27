import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

SIZES = [36, 72, 108, 144]
COUNT = 100
WORKERS = max(1, (os.cpu_count() or 2) // 2)


def generate(seed: int) -> tuple[int, int, int]:
    size = SIZES[seed % len(SIZES)]
    cmd = [
        "uv", "run", "python", "-m", "vcmi_mapgen.cli", "generate",
        "--seed", str(seed),
        "--size", str(size),
        "--players", "4",
        "--teams", "2v2",
        "--no-water",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"seed {seed} size {size} failed:\n{result.stderr[-2000:]}", file=sys.stderr)
    return seed, size, result.returncode


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else COUNT
    failed = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for seed, size, code in pool.map(generate, range(1, count + 1)):
            failed += code != 0
            print(f"seed {seed:3d} size {size:3d} {'ok' if code == 0 else 'FAILED'}", flush=True)
    print(f"{count - failed}/{count} maps in out/")


if __name__ == "__main__":
    main()
