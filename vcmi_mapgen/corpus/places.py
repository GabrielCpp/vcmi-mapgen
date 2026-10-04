"""Load and save the place statistics in ``data/pp/place_stats.json`` and
``data/pp/place_stats_underground.json``."""

from pathlib import Path

from vcmi_mapgen.core.model import JsonValue
from vcmi_mapgen.core.priors.places import (
    PaletteCount,
    PlaceContent,
    PlaceCount,
    PlaceStats,
    RoadCount,
    RoadStats,
)
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

SOURCE = "vcmi_mapgen.corpus.mine.places.mine_places"
DIGITS = 4


def _float(value: JsonValue) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _floats(value: JsonValue | None) -> tuple[float, ...]:
    return tuple(_float(v) for v in jv.as_list(value))


def _ints(value: JsonValue | None) -> tuple[int, ...]:
    return tuple(jv.as_int(v) for v in jv.as_list(value))


def _tally(value: JsonValue | None) -> dict[str, int]:
    return {k: jv.as_int(v) for k, v in jv.as_object(value).items()}


def _count(value: JsonValue) -> PlaceCount:
    places, players, land = _ints(value)
    return PlaceCount(places, players, land)


def _palette(value: JsonValue) -> PaletteCount:
    regions, places, land = _ints(value)
    return PaletteCount(regions, places, land)


def _pair(value: JsonValue) -> tuple[int, int]:
    same, total = _ints(value)
    return same, total


def _content(value: JsonValue) -> PlaceContent:
    role, hop, area, rewards, val, fixed, guards = jv.as_list(value)
    return PlaceContent(
        jv.as_str(role),
        jv.as_int(hop),
        jv.as_int(area),
        jv.as_int(rewards),
        jv.as_int(val),
        _ints(guards),
        jv.as_int(fixed),
    )


def _content_row(c: PlaceContent) -> list[object]:
    return [c.role, c.hop, c.area, c.rewards, c.value, c.fixed, list(c.guards)]


def _roads_from_json(raw: JsonValue | None) -> RoadStats:
    obj = jv.as_object(raw)
    return RoadStats(
        counts=tuple(RoadCount(*_ints(v)) for v in jv.as_list(obj.get("counts"))),
        crossed={k: _pair(v) for k, v in jv.as_object(obj.get("crossed")).items()},
        surface={
            int(h): {int(r): n for r, n in _tally(v).items()}
            for h, v in jv.as_object(obj.get("surface")).items()
        },
        on_dominant=_pair(obj.get("on_dominant", [0, 0])),
        land_dominant=_pair(obj.get("land_dominant", [0, 0])),
        near=_pair(obj.get("near", [0, 0])),
    )


def _roads_to_json(st: RoadStats) -> dict[str, object]:
    return {
        "counts": [
            [c.road, c.walk, c.towns, c.joined, c.linked, c.homes, c.home_joined] for c in st.counts
        ],
        "crossed": {k: list(v) for k, v in st.crossed.items()},
        "surface": {str(h): {str(r): n for r, n in v.items()} for h, v in st.surface.items()},
        "on_dominant": list(st.on_dominant),
        "land_dominant": list(st.land_dominant),
        "near": list(st.near),
    }


def _stats_from_json(raw: JsonValue) -> PlaceStats:
    obj = jv.as_object(raw)
    per_role = {
        key: {role: _floats(v) for role, v in jv.as_object(obj.get(key)).items()}
        for key in ("rel_size", "compactness", "roughness", "dominant_share")
    }
    return PlaceStats(
        counts=tuple(_count(v) for v in jv.as_list(obj.get("counts"))),
        rel_size=per_role["rel_size"],
        adjacency=_tally(obj.get("adjacency")),
        degree={role: _ints(v) for role, v in jv.as_object(obj.get("degree")).items()},
        home_separation=_floats(obj.get("home_separation")),
        compactness=per_role["compactness"],
        roughness=per_role["roughness"],
        dominant={
            role: {int(t): n for t, n in _tally(v).items()}
            for role, v in jv.as_object(obj.get("dominant")).items()
        },
        dominant_share=per_role["dominant_share"],
        border_kinds=_tally(obj.get("border_kinds")),
        barrier_depth=_floats(obj.get("barrier_depth")),
        accent_rate={int(t): _floats(v) for t, v in jv.as_object(obj.get("accent_rate")).items()},
        accent_size={int(t): _ints(v) for t, v in jv.as_object(obj.get("accent_size")).items()},
        transition_width=_ints(obj.get("transition_width")),
        raw_cut=_floats(obj.get("raw_cut")),
        palette_counts=tuple(_palette(v) for v in jv.as_list(obj.get("palette_counts"))),
        same_by_roles={k: _pair(v) for k, v in jv.as_object(obj.get("same_by_roles")).items()},
        content=tuple(_content(v) for v in jv.as_list(obj.get("content"))),
        roads=_roads_from_json(obj.get("roads")),
    )


def _rounded(values: tuple[float, ...]) -> list[float]:
    return [round(v, DIGITS) for v in values]


def _stats_to_json(st: PlaceStats) -> dict[str, object]:
    return {
        "counts": [[c.places, c.players, c.land] for c in st.counts],
        "rel_size": {k: _rounded(v) for k, v in st.rel_size.items()},
        "adjacency": dict(st.adjacency),
        "degree": {k: list(v) for k, v in st.degree.items()},
        "home_separation": _rounded(st.home_separation),
        "compactness": {k: _rounded(v) for k, v in st.compactness.items()},
        "roughness": {k: _rounded(v) for k, v in st.roughness.items()},
        "dominant": {k: {str(t): n for t, n in v.items()} for k, v in st.dominant.items()},
        "dominant_share": {k: _rounded(v) for k, v in st.dominant_share.items()},
        "border_kinds": dict(st.border_kinds),
        "barrier_depth": _rounded(st.barrier_depth),
        "accent_rate": {str(t): _rounded(v) for t, v in st.accent_rate.items()},
        "accent_size": {str(t): list(v) for t, v in st.accent_size.items()},
        "transition_width": list(st.transition_width),
        "raw_cut": _rounded(st.raw_cut),
        "palette_counts": [[c.regions, c.places, c.land] for c in st.palette_counts],
        "same_by_roles": {k: list(v) for k, v in st.same_by_roles.items()},
        "content": [_content_row(c) for c in st.content],
        "roads": _roads_to_json(st.roads),
    }


def _stats_path(pp_dir: Path, level: int) -> Path:
    return pp_dir / ("place_stats.json" if level == 0 else "place_stats_underground.json")


def load_places(pp_dir: Path, level: int = 0) -> PlaceStats:
    return _stats_from_json(cache.read(_stats_path(pp_dir, level)))


def save_places(pp_dir: Path, level: int, st: PlaceStats) -> None:
    cache.write(_stats_path(pp_dir, level), SOURCE, _stats_to_json(st))
