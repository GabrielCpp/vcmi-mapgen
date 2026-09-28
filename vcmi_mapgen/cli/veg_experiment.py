import argparse

from vcmi_mapgen.cli.settings import Settings, load_settings
from vcmi_mapgen.core.grid.geometry import run_lengths
from vcmi_mapgen.core.grid.segment import segment_level
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.sample import build_model, sample_zone
from vcmi_mapgen.corpus.maps import load_corpus_map
from vcmi_mapgen.corpus.vegetation import load_vegetation
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.terrain import name_of


def m1_experiment(settings: Settings, map_name: str, zid: int, seed: int = 1) -> None:
    """The spec's decisive M1 test: sample vegetation for a REAL corpus zone with NO lattice
    field and compare the EMERGENT run-length histogram + coverage against the corpus."""
    fm = load_corpus_map(settings.maps_dir, map_name)
    zones, zone_label, _ = segment_level(fm.terrain[0])
    z = zones[zid]
    terrain = name_of(z.terrain_type)
    ts = set(z.tiles_set)
    model = build_model(VcmiCatalog(), terrain, load_vegetation(settings.pp_dir, terrain))
    head = f"model[{terrain}]: {len(model.cats)} categories, "
    print(f"{head}target veg_blocked_frac={model.target:.3f}")

    objs, blocked, _prot = sample_zone(ZoneRef(ts, zone_label, zid, z.centroid), model, seed=seed)
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
    m1_experiment(load_settings(), args.map, args.zone, seed=args.seed)


if __name__ == "__main__":
    main()
