import argparse

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.geometry import run_lengths
from vcmi_mapgen.kit.segmentation import segment_level
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.steps.vegetation.sample import ZoneRef, build_model, sample_zone


def m1_experiment(map_name: str, zid: int, seed: int = 1) -> None:
    """The spec's decisive M1 test: sample vegetation for a REAL corpus zone with NO lattice
    field and compare the EMERGENT run-length histogram + coverage against the corpus."""
    fm = OR.load_faithful(map_name)
    zones, _zl, _ = segment_level(fm.terrain[0])
    z = zones[zid]
    terrain = TNAME[z.terrain_type]
    ts = set(z.tiles_set)
    model = build_model(terrain)
    head = f"model[{terrain}]: {len(model.cats)} categories, "
    print(f"{head}target veg_blocked_frac={model.target:.3f}")

    objs, blocked, _prot = sample_zone(ZoneRef(ts, zones, zid), model, seed=seed)
    frac = len(blocked) / len(ts)
    zhead = f"zone {zid} ({terrain}, {len(ts)} tiles): {len(objs)} objects, "
    print(f"{zhead}blocked frac gen={frac:.3f} corpus={model.target:.3f}")

    hg = run_lengths(ts, ts - blocked)
    sg = sum(hg.values()) or 1
    print("veg-only open run-length  k:  corpus%   gen%")
    for k in range(1, 9):
        cor = 100 * model.runs.get(str(k), 0.0)
        print(f"   {k}: {cor:6.1f}  {100 * hg.get(k, 0) / sg:6.1f}")


class _Args(argparse.Namespace):
    map: str = "All for One"
    zone: int = 11
    seed: int = 1


def main() -> None:
    ap = argparse.ArgumentParser()
    _ = ap.add_argument("--map", default="All for One")
    _ = ap.add_argument("--zone", type=int, default=11)
    _ = ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(namespace=_Args())
    m1_experiment(args.map, args.zone, seed=args.seed)


if __name__ == "__main__":
    main()
