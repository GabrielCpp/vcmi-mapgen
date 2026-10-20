"""Load and save the spacing law of each kind in ``data/pp/spacing.json``."""

from collections.abc import Mapping
from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.spacing import SpacingFit, SpacingPriors
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

SPACING_FILE = "spacing.json"
SPACING_VERSION = 1
SPACING_SOURCE = "vcmi_mapgen.corpus.mine.spacing.mine_spacing"


def _floats(value: JsonValue | None) -> tuple[float, ...]:
    return tuple(jv.as_float(v) for v in jv.as_list(value))


def _fit(value: JsonValue | None) -> SpacingFit:
    f = jv.as_object(value)
    return SpacingFit(
        family=jv.as_str(f.get("family")),
        params=_floats(f.get("params")),
        n=jv.as_int(f.get("n")),
        p10=jv.as_float(f.get("p10")),
        p50=jv.as_float(f.get("p50")),
        p90=jv.as_float(f.get("p90")),
        aic=jv.as_float(f.get("aic")),
        chi_p=jv.as_float(f.get("chi_p")),
        samples=_floats(f.get("samples")),
    )


def _fits(value: JsonValue | None) -> dict[str, SpacingFit]:
    return {key: _fit(f) for key, f in jv.as_object(value).items()}


def _dump(fit: SpacingFit) -> dict[str, object]:
    return {
        "family": fit.family,
        "params": list(fit.params),
        "n": fit.n,
        "p10": fit.p10,
        "p50": fit.p50,
        "p90": fit.p90,
        "aic": fit.aic,
        "chi_p": fit.chi_p,
        "samples": list(fit.samples),
    }


def _dumps(fits: Mapping[str, SpacingFit]) -> dict[str, object]:
    return {key: _dump(fits[key]) for key in sorted(fits)}


def load_spacing(pp_dir: Path) -> SpacingPriors:
    """The spacing fits in ``spacing.json``, or none when the file is absent."""
    if not (pp_dir / SPACING_FILE).exists():
        return SpacingPriors()
    st = cache.read(pp_dir / SPACING_FILE, version=SPACING_VERSION)
    return SpacingPriors(_fits(st.get("kinds")), _fits(st.get("pools")))


def save_spacing(pp_dir: Path, st: SpacingPriors) -> None:
    cache.write(
        pp_dir / SPACING_FILE,
        SPACING_SOURCE,
        {
            "_version": SPACING_VERSION,
            "kinds": _dumps(st.kinds),
            "pools": _dumps(st.pools),
        },
    )
