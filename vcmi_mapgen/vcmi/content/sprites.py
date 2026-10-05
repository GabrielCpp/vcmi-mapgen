"""`SpriteSource`: an object's picture from the base game, else from an enabled mod."""

from collections.abc import Sequence
from typing import final

from vcmi_mapgen.vcmi.content.archive import ContentArchive

SPRITES_DIR = "sprites"
DEF_SUFFIX = ".def"


@final
class SpriteSource:
    """Reads a sprite from ``base``, then from ``SPRITES_DIR`` of each mod archive in turn."""

    def __init__(self, base: ContentArchive, mods: Sequence[ContentArchive] = ()) -> None:
        self.base = base
        self.mods = tuple(mods)

    def read(self, name: str) -> bytes | None:
        found = self.base.read(name)
        if found is not None or not self.mods:
            return found
        path = name if name.lower().endswith(DEF_SUFFIX) else f"{name}{DEF_SUFFIX}"
        return next(
            (b for b in (m.read(f"{SPRITES_DIR}/{path}") for m in self.mods) if b is not None),
            None,
        )
