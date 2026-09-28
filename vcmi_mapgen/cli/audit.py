"""`audit`: report the corpus objects the generator cannot reproduce, or print the gameplay
densities it draws from."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model.purpose import PICKUP_PURPOSES, VISIT_PURPOSES, Purpose
from vcmi_mapgen.corpus.gameplay import load_gameplay
from vcmi_mapgen.corpus.mine.gameplay import land_names


@dataclass(frozen=True, slots=True)
class AuditGap:
    purpose: str
    anim: str
    count: int
    why: str


# purposes deliberately NOT reproduced by the generator (the audit's whitelist)
AUDIT_EXCLUDED = {
    Purpose.TRANSPORT: "relational: subterranean gates + two-way monoliths are placed by their own "
    + "matched-set passes (place_gate_pairs / PortalStep), not the "
    + "per-zone density draw — the audit must not demand every corpus variant",
    Purpose.GUARD: "guards are leveled RANDOM monsters by design, never corpus identities",
}
# corpus sprite VARIANTS of catalog objects: same {type, subtype} gameplay object under a
# different DEF filename (fort-less 'village' town sprites vs the editor's forted '..x0'
# sprite; the corpus's "AVGnoll" gnoll-hut DEF vs the editor table's "avggnll0") — the audit
# treats them as reachable through their canonical animation.
TOWN_SPRITE_VARIANTS = {
    "avcrand0": "avcranx0",
    "avccast0": "avccasx0",
    "avcramp0": "avcramx0",
    "avctowr0": "avctowx0",
    "avcinft0": "avcinfx0",
    "avcnecr0": "avcnecx0",
    "avcdung0": "avcdunx0",
    "avcstro0": "avcstrx0",
    "avcftrt0": "avcftrx0",
    "avchfor0": "avchforx",
    "avgnoll": "avggnll0",
}
# purposes the generator actually places on land (BANK included since the land-bank change)
PLACED_PURPOSES = (
    set(VISIT_PURPOSES)
    | set(PICKUP_PURPOSES)
    | {Purpose.TOWN, Purpose.MINE, Purpose.DWELLING, Purpose.BANK, Purpose.WATER_TRANSPORT}
) - set(AUDIT_EXCLUDED)


def audit_variety(catalog: Catalog, pp_dir: Path, level: int = 0) -> list[AuditGap]:
    """Corpus-variety audit: every (purpose, animation) with a nonzero corpus count on land
    must (a) resolve through the catalog and (b) be reachable through a generator pool —
    i.e. its purpose is placed and the animation sits in `gameplay_pool` for at least one
    land terrain (or it is an editor RANDOM class, placed by convention). Returns a list of
    `AuditGap`s (empty = the generated maps can reach the corpus's full visitable variety).
    `level` selects which level's corpus stats table to audit (0 = surface, 1 = underground:
    both must stay green since `--subterrain` places gameplay from the level-1 table too)."""
    st = load_gameplay(pp_dir, level)
    land = land_names(catalog)
    seen: dict[tuple[str, str], int] = {}  # (purpose, anim) -> total corpus count
    for terr in land:
        for p, anims in st[terr].anim_w.items():
            if p in AUDIT_EXCLUDED:
                continue
            for anim, cnt in anims.items():
                seen[(p, anim)] = seen.get((p, anim), 0) + cnt
    pool_anims: dict[str, set[str]] = {}  # purpose -> anims reachable on ANY terrain incl water
    for p in {p for p, _a in seen}:
        pool_anims[p] = {i.kind.lower() for t in (*land, "water") for i in catalog.candidates(p, t)}
    gaps: list[AuditGap] = []
    for (p, raw_anim), cnt in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
        anim = TOWN_SPRITE_VARIANTS.get(raw_anim, raw_anim)
        ident = catalog.identity_of(anim)
        if catalog.spec(anim) is None:
            gaps.append(AuditGap(p, anim, cnt, "animation missing from the catalog"))
        elif p not in PLACED_PURPOSES:
            gaps.append(AuditGap(p, anim, cnt, f"purpose {p} not placed by the generator"))
        elif "random" not in (ident.type or "").lower() and anim not in pool_anims[p]:
            gaps.append(AuditGap(p, anim, cnt, "not in pool for any land terrain"))
    return gaps


def audit(catalog: Catalog, pp_dir: Path, levels: Sequence[int]) -> bool:
    """Print the variety gaps of each level. True when every level is gap-free."""
    ok = True
    for lvl in levels:
        gaps = audit_variety(catalog, pp_dir, lvl)
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


def densities(catalog: Catalog, pp_dir: Path, level: int) -> None:
    """Print each land terrain's per-purpose density, border openness and guard fractions."""
    st = load_gameplay(pp_dir, level)
    for t in land_names(catalog):
        d = st[t]
        dens = {p: round(c / max(d.tiles, 1) * 1000, 2) for p, c in d.counts.items()}
        print(
            f"{t:<8} tiles={d.tiles:>7}  per-1000-tiles: {dens}  "
            + f"border_open={d.border_open_frac:.2f}"
        )
        print(f"         guard_frac={d.guard_frac}")
