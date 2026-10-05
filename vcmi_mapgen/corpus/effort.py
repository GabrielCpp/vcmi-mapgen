"""Load and save the guard toll, the effort band edges and each band's offer in
``data/pp/effort.json``."""

from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.priors.effort import (
    DEFAULT_BOXES,
    DEFAULT_GRANTS,
    Basket,
    EffortPriors,
    RewardTier,
)
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

EFFORT_FILE = "effort.json"


EFFORT_VERSION = 1


EFFORT_SOURCE = "vcmi_mapgen.corpus.mine.effort.mine_effort"


def _basket(value: JsonValue) -> Basket:
    obj = jv.as_object(value)
    out: dict[ArtifactTier, int] = {t: jv.as_int(obj.get(t)) for t in TIERS if t in obj}
    return out


def _ints(value: JsonValue) -> tuple[int, ...]:
    return tuple(jv.as_int(n) for n in jv.as_list(value))


def _grant(value: JsonValue) -> RewardTier:
    obj = jv.as_object(value)
    w, c = _ints(obj.get("weights")), _ints(obj.get("creatures"))
    return RewardTier(
        (w[0], w[1], w[2]),
        _ints(obj.get("gold")),
        _ints(obj.get("experience")),
        (c[0], c[1]),
        _ints(obj.get("levels")),
    )


def _grant_json(g: RewardTier) -> JsonValue:
    return {
        "weights": list(g.weights),
        "gold": list(g.gold),
        "experience": list(g.experience),
        "creatures": list(g.creatures),
        "levels": list(g.levels),
    }


def load_effort(pp_dir: Path) -> EffortPriors:
    st = cache.read(pp_dir / EFFORT_FILE, version=EFFORT_VERSION)
    medians = jv.as_object(st.get("medians"))
    counts = jv.as_object(st.get("counts"))
    return EffortPriors(
        toll=tuple(jv.as_int(n) for n in jv.as_list(st.get("toll"))),
        edges=tuple(jv.as_int(n) for n in jv.as_list(st.get("edges"))),
        baskets=tuple(_basket(b) for b in jv.as_list(st.get("baskets"))),
        grants=tuple(_grant(g) for g in jv.as_list(st["grants"]))
        if "grants" in st
        else DEFAULT_GRANTS,
        boxes=_ints(st["boxes"]) if "boxes" in st else DEFAULT_BOXES,
        medians={t: float(v) for t in TIERS if isinstance(v := medians.get(t), int | float)},
        counts={t: jv.as_int(counts.get(t)) for t in TIERS if t in counts},
    )


def save_effort(pp_dir: Path, st: EffortPriors) -> None:
    cache.write(
        pp_dir / EFFORT_FILE,
        EFFORT_SOURCE,
        {
            "_version": EFFORT_VERSION,
            "toll": list(st.toll),
            "edges": list(st.edges),
            "baskets": [dict(b) for b in st.baskets],
            "grants": [_grant_json(g) for g in st.grants],
            "boxes": list(st.boxes),
            "medians": dict(st.medians),
            "counts": dict(st.counts),
        },
    )


def tuned_effort(pp_dir: Path) -> EffortPriors:
    """The effort priors the user keeps in ``effort.json``, or the defaults when it is
    absent. The miner keeps their toll, baskets, grants and boxes."""
    if not (pp_dir / EFFORT_FILE).exists():
        return EffortPriors()
    return load_effort(pp_dir)
