"""`audit`: report the corpus objects the generator cannot reproduce, or print the gameplay
densities it draws from."""

from collections.abc import Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.steps.gameplay.mines import (
    AUDIT_EXCLUDED,
    audit_variety,
    land_names,
    load_gameplay,
)


def audit(catalog: Catalog, levels: Sequence[int]) -> bool:
    """Print the variety gaps of each level. True when every level is gap-free."""
    ok = True
    for lvl in levels:
        gaps = audit_variety(catalog, level=lvl)
        print(f"-- level {lvl} --")
        for reason, note in AUDIT_EXCLUDED.items():
            print(f"excluded {reason}: {note}")
        if not gaps:
            print("AUDIT OK: every corpus (purpose, animation) on land is reachable")
            continue
        ok = False
        print(f"AUDIT: {len(gaps)} gaps")
        for g in gaps:
            print(f"  {g.purpose:<15} {g.anim:<10} corpus n={g.count:>5}  {g.why}")
    return ok


def densities(catalog: Catalog, level: int) -> None:
    """Print each land terrain's per-purpose density, border openness and guard fractions."""
    st = load_gameplay(level=level)
    for t in land_names(catalog):
        d = st[t]
        dens = {p: round(c / max(d.tiles, 1) * 1000, 2) for p, c in d.counts.items()}
        print(
            f"{t:<8} tiles={d.tiles:>7}  per-1000-tiles: {dens}  "
            + f"border_open={d.border_open_frac:.2f}"
        )
        print(f"         guard_frac={d.guard_frac}")
