"""Print one terrain's mined vegetation statistics.

uv run python -m vcmi_mapgen.cli.veg_report --report grass
"""

import argparse
from pathlib import Path

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.priors.vegetation import VegetationStats, theta
from vcmi_mapgen.corpus.vegetation import load_vegetation


def report(pp_dir: Path, terrain: str) -> tuple[VegetationStats, dict[str, list[float]]]:
    st = load_vegetation(pp_dir, terrain)
    head = f"== {terrain}: zones={st.nzones} tiles={st.tiles} anchors={st.nanchors} "
    density = f"(density {st.nanchors / max(st.tiles, 1):.3f}/tile) "
    print(f"{head}{density}veg_blocked_frac={st.veg_blocked_frac:.3f}")
    lam_tot = st.lam_tot
    top = sorted(lam_tot, key=lambda name: lam_tot[name], reverse=True)[:8]
    print("  intensity by edge bin (anchors/tile):")
    for cat in top:
        row = " ".join(f"{v:.3f}" for v in st.lam[cat])
        print(f"    {cat:<18} tot={lam_tot[cat]:.4f}  by-ebin {row}")
    th = theta(st)
    print("  pair correlation g(r), r=0..6  (same-category):")
    for cat in top[:6]:
        key = f"{cat}|{cat}"
        if key in st.g:
            row = " ".join(f"{v:6.2f}" for v in st.g[key])
            print(f"    {cat:<18} {row}")
    print("  corpus veg-only open run-length fractions:", st.runs)
    return st, th


class _Args(argparse.Namespace):
    report: str = ""


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("--report", metavar="TERRAIN", required=True)
    args = ap.parse_args(namespace=_Args())
    _ = report(load_settings().pp_dir, args.report)


if __name__ == "__main__":
    main()
