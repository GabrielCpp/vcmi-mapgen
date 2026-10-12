"""Load and save the corpus count curves: the resource mines in ``data/pp/mines.json``, the
towns in ``data/pp/towns.json``, the keymaster tents in ``data/pp/keymasters.json``, the
two-way monolith pairs in ``data/pp/portals.json`` and every gameplay family in
``data/pp/families.json``."""

from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves, FamilyFit
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

MINES_FILE = "mines.json"
TOWNS_FILE = "towns.json"
KEYMASTERS_FILE = "keymasters.json"
PORTALS_FILE = "portals.json"
FAMILIES_FILE = "families.json"
CURVE_VERSION = 1
FAMILIES_VERSION = 2
MINES_SOURCE = "vcmi_mapgen.corpus.mine.counts.mine_curve"
TOWNS_SOURCE = "vcmi_mapgen.corpus.mine.counts.town_curve"
KEYMASTERS_SOURCE = "vcmi_mapgen.corpus.mine.counts.keymaster_curve"
PORTALS_SOURCE = "vcmi_mapgen.corpus.mine.counts.portal_curve"
FAMILIES_SOURCE = "vcmi_mapgen.corpus.mine.counts.family_curves"


def load_curve(pp_dir: Path, name: str) -> CountCurve:
    st = cache.read(pp_dir / name, version=CURVE_VERSION)
    return CountCurve(
        jv.as_float(st.get("intercept")),
        jv.as_float(st.get("land_exp")),
        jv.as_float(st.get("players_exp")),
    )


def save_curve(pp_dir: Path, name: str, source: str, curve: CountCurve) -> None:
    cache.write(
        pp_dir / name,
        source,
        {
            "_version": CURVE_VERSION,
            "intercept": curve.intercept,
            "land_exp": curve.land_exp,
            "players_exp": curve.players_exp,
        },
    )


def _fit(value: JsonValue) -> FamilyFit:
    obj = jv.as_object(value)
    curve = CountCurve(
        jv.as_float(obj.get("intercept")),
        jv.as_float(obj.get("land_exp")),
        jv.as_float(obj.get("players_exp")),
    )
    guards = tuple(jv.as_float(g) for g in jv.as_list(obj.get("guards")))
    return FamilyFit(curve, jv.as_float(obj.get("stretch")), guards)


def _fit_json(fit: FamilyFit) -> JsonValue:
    return {
        "intercept": fit.count.intercept,
        "land_exp": fit.count.land_exp,
        "players_exp": fit.count.players_exp,
        "stretch": fit.stretch,
        "guards": list(fit.guards),
    }


def load_families(pp_dir: Path) -> FamilyCurves:
    """The family curves in ``families.json``, or none when the file is absent."""
    if not (pp_dir / FAMILIES_FILE).exists():
        return FamilyCurves()
    st = cache.read(pp_dir / FAMILIES_FILE, version=FAMILIES_VERSION)
    return FamilyCurves(
        jv.as_int(st.get("land_ref")),
        {f: _fit(v) for f, v in jv.as_object(st.get("families")).items()},
    )


def save_families(pp_dir: Path, curves: FamilyCurves) -> None:
    cache.write(
        pp_dir / FAMILIES_FILE,
        FAMILIES_SOURCE,
        {
            "_version": FAMILIES_VERSION,
            "land_ref": curves.land_ref,
            "families": {f: _fit_json(v) for f, v in sorted(curves.fits.items())},
        },
    )
