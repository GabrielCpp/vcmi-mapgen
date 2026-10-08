"""`ModObject`: one placeable template an enabled mod declares in its own object config."""

from collections.abc import Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, JsonValue
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi import terrain as VT
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.catalog import tables as TB
from vcmi_mapgen.vcmi.content.archive import ContentArchive, open_archive
from vcmi_mapgen.vcmi.content.manifest import ModManifest
from vcmi_mapgen.vcmi.footprint import footprint_of, sealed
from vcmi_mapgen.vcmi.formats import json_value as jv

REWARDS = "REWARDS"
_BODY = frozenset("BH")
_VISIT = frozenset("AT")
_NOT_LAND = ("water", "")


@dataclass(frozen=True, slots=True)
class ModObject:
    """One template of a mod object: the mod that declares it, its identity, its VCMI mask
    and approach grid, the terrains it stands on (``None`` for any land), the purpose it is
    placed for and its price. An object with no price, or one whose purpose mods may not
    feed, has no purpose and is never placed."""

    mod_id: str
    identity: Identity
    mask: tuple[str, ...]
    visitable_from: tuple[str, ...] | None
    terrains: frozenset[str] | None
    purpose: Purpose | None
    price: int | None

    def stands_on(self, terrain: str) -> bool:
        if self.terrains is None:
            return terrain not in _NOT_LAND
        return terrain in self.terrains


def _inherit(child: JsonValue | None, base: JsonValue | None) -> JsonValue | None:
    if not isinstance(child, dict) or not isinstance(base, dict):
        return base if child is None else child
    merged = dict(base)
    for key, value in child.items():
        merged[key] = _inherit(value, base.get(key))
    return merged


def _engine_mask(mask: Sequence[str]) -> tuple[str, ...]:
    visit = "X" if any(ch in _BODY for row in mask for ch in row) else "A"
    chars = {"B": "B", "H": "B", "V": "V", "A": visit, "T": visit}
    return tuple("".join(chars.get(ch, " ") for ch in row) for row in mask)


def _reward_purpose(rewards: JsonValue | None) -> Purpose | None:
    keys = {key for reward in jv.as_list(rewards) for key in jv.as_object(reward)}
    rules = TB.mod_purposes()["rewards"]
    return next((Purpose(p) for key, p in rules if key in keys), None)


def _purpose(key: str, handler: str | None, kind: dict[str, JsonValue]) -> Purpose | None:
    if ":" in key or handler is None:
        return OB.purpose_of_type(key.rpartition(":")[2])
    rule = TB.mod_purposes()["handlers"].get(handler)
    if rule == REWARDS:
        return _reward_purpose(kind.get("rewards"))
    return None if rule is None else Purpose(rule)


def _price(kind: dict[str, JsonValue]) -> int | None:
    value = jv.opt_int(jv.as_object(kind.get("rmg")).get("value"))
    return value if value is not None and value > 0 else None


def _terrains(template: dict[str, JsonValue]) -> frozenset[str] | None:
    ids = jv.opt_str_list(template.get("allowedTerrains"))
    if ids is None:
        return None
    return frozenset(VT.BY_CONFIG_ID[i] for i in ids if i in VT.BY_CONFIG_ID)


@dataclass(frozen=True, slots=True)
class _Kind:
    """One object type of a mod's config, its class base already merged in."""

    mod_id: str
    type: str
    subtype: str
    purpose: Purpose | None
    price: int | None
    data: dict[str, JsonValue]


def _entry(kind: _Kind, template: dict[str, JsonValue]) -> ModObject | None:
    animation = jv.as_str(template.get("animation"))
    mask = tuple(jv.str_list(template.get("mask")))
    if not animation or not mask:
        return None
    visits = any(ch in _VISIT for row in mask for ch in row)
    joins = kind.purpose is not None and kind.purpose in TB.mod_purposes()["joins"]
    placed = visits and joins and kind.price is not None
    engine = _engine_mask(mask)
    footprint = footprint_of(engine if OB.is_vanish_type(kind.type) else sealed(engine))
    from_ = jv.opt_str_list(template.get("visitableFrom"))
    return ModObject(
        kind.mod_id,
        Identity(kind.type, kind.subtype, animation, footprint),
        mask,
        None if from_ is None else tuple(from_),
        _terrains(template),
        kind.purpose if placed else None,
        kind.price,
    )


def _kinds(mod_id: str, config: dict[str, JsonValue]) -> Iterator[_Kind]:
    for key, raw in config.items():
        cls = jv.as_object(raw)
        handler = cls.get("handler")
        for subtype, kind_raw in jv.as_object(cls.get("types")).items():
            data = jv.as_object(_inherit(kind_raw, cls.get("base")))
            purpose = _purpose(key, handler if isinstance(handler, str) else None, data)
            yield _Kind(mod_id, key.rpartition(":")[2], subtype, purpose, _price(data), data)


def _templates(kind: _Kind) -> Iterator[dict[str, JsonValue]]:
    base = kind.data.get("base")
    for template in jv.as_object(kind.data.get("templates")).values():
        yield jv.as_object(_inherit(template, base))


def _configs(manifest: ModManifest, archive: ContentArchive) -> Iterator[dict[str, JsonValue]]:
    for path in manifest.objects:
        name = path if path.lower().endswith(".json") else f"{path}.json"
        raw = archive.read(name)
        if raw is not None:
            yield jv.as_object(jv.loads_relaxed(raw.decode("utf-8-sig")))


def mod_objects(manifests: Mapping[str, ModManifest], mods: AbstractSet[str]) -> list[ModObject]:
    """Every object template the enabled ``mods`` declare, mods in id order and each mod's
    templates in its config order. The first template of an animation wins."""
    found: dict[str, ModObject] = {}
    for mod_id in sorted(m for m in mods if m in manifests):
        manifest = manifests[mod_id]
        for config in _configs(manifest, open_archive(manifest.folder)):
            for kind in _kinds(mod_id, config):
                for template in _templates(kind):
                    entry = _entry(kind, template)
                    if entry is not None:
                        _ = found.setdefault(entry.identity.kind.lower(), entry)
    return list(found.values())
