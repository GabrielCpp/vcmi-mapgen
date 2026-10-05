"""`SpriteSource`: an object's picture from the base game, else from an enabled mod."""

from collections.abc import Sequence
from typing import final

from vcmi_mapgen.vcmi.content.archive import ContentArchive

SPRITES_DIR = "sprites"
DEF_SUFFIX = ".def"
SUFFIXES = (DEF_SUFFIX, ".json", ".png")


@final
class SpriteSource:
    """Reads a sprite from ``base``, then from ``SPRITES_DIR`` of each mod archive in turn.
    A name with no suffix is a `.def`. A `.json` animation or one of its `.png` frames is
    read as named."""

    def __init__(self, base: ContentArchive, mods: Sequence[ContentArchive] = ()) -> None:
        self.base = base
        self.mods = tuple(mods)

    def read(self, name: str) -> bytes | None:
        found = self.base.read(name)
        if found is not None or not self.mods:
            return found
        path = name if name.lower().endswith(SUFFIXES) else f"{name}{DEF_SUFFIX}"
        return next(
            (b for b in (m.read(f"{SPRITES_DIR}/{path}") for m in self.mods) if b is not None),
            None,
        )
