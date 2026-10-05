"""`ModContent`: what the enabled mods add to the base game, read once per run."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Identity, JsonValue
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.content.archive import ContentArchive, open_archive
from vcmi_mapgen.vcmi.content.enabled import EnabledSet
from vcmi_mapgen.vcmi.content.manifest import ModManifest
from vcmi_mapgen.vcmi.content.objects import ModObject, mod_objects


@dataclass(frozen=True, slots=True)
class ModContent:
    """The manifests of the enabled mods by id and their object templates by lowercased
    animation. Empty for the base game."""

    manifests: Mapping[str, ModManifest] = field(default_factory=dict[str, ModManifest])
    objects: Mapping[str, ModObject] = field(default_factory=dict[str, ModObject])

    def object(self, kind: str) -> ModObject | None:
        return self.objects.get(kind.lower()) if self.objects else None

    def pool(self, purpose: str, terrain: str) -> list[Identity]:
        """The placeable templates for ``purpose`` that stand on ``terrain``, by animation."""
        found = [
            o.identity
            for o in self.objects.values()
            if o.purpose == purpose and o.stands_on(terrain)
        ]
        return sorted(found, key=lambda i: i.kind)

    def archives(self) -> list[ContentArchive]:
        return [open_archive(self.manifests[m].folder) for m in sorted(self.manifests)]

    def requirement(self, kinds: Iterable[str]) -> list[JsonValue]:
        """The header's mods list for a map holding ``kinds``: each mod an object comes from
        and that mod's parents, by id."""
        needed: set[str] = set()
        for kind in kinds:
            entry = self.object(kind)
            mod_id = entry.mod_id if entry else None
            while mod_id is not None and mod_id not in needed:
                needed.add(mod_id)
                mod_id = self.manifests[mod_id].parent
        return [_declared(self.manifests[m]) for m in sorted(needed)]


def _declared(manifest: ModManifest) -> JsonValue:
    entry: dict[str, JsonValue] = {"modId": manifest.mod_id, "name": manifest.name}
    if manifest.parent:
        entry["parent"] = manifest.parent
    entry["version"] = manifest.version
    return entry


NO_MODS = ModContent()


def load_mods(manifests: Mapping[str, ModManifest], enabled: EnabledSet) -> ModContent:
    """The content of every enabled mod in ``manifests``. A template whose animation the
    base game already holds stays the base game's, so it never makes a map need the mod."""
    kept = {m: manifests[m] for m in sorted(enabled.mods) if m in manifests}
    found = mod_objects(kept, frozenset(kept))
    own = [o for o in found if not OB.has_animation(o.identity.kind)]
    return ModContent(kept, {o.identity.kind.lower(): o for o in own})
