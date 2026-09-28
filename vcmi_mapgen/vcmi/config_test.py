"""Reliability test for vcmi.config.VcmiConfig.resolve().

Requires a local VCMI install (config/objects, config/creatures, ... on disk); skipped
otherwise, same gating pattern as sprites_test.py's H3 sprite LOD check.
"""

import pytest

from vcmi_mapgen.conftest import find_install
from vcmi_mapgen.vcmi.config import VcmiConfig, load_config

_INSTALL = find_install()
CONFIG = load_config(_INSTALL) if _INSTALL is not None else VcmiConfig()

pytestmark = pytest.mark.skipif(
    not CONFIG.classes, reason="no local VCMI install config/ tree found"
)

# (objectClass, objectSubID) -> expected (type, subtype), captured from a real VCMI
# install's config — covers an inline-subtype object, the creature/faction/artifact
# indirection paths, and a typeless object.
KNOWN = {
    (134, 0): ("mountain", "object"),
    (101, 0): ("treasureChest", "treasureChest"),
    (53, 6): ("mine", "goldMine"),
    (79, 6): ("resource", "gold"),
    (54, 0): ("monster", "pikeman"),
    (98, 0): ("town", "castle"),
    (45, 2): ("monolithTwoWay", "monolith3"),
    (5, 0): ("artifact", "spellBook"),
}


@pytest.mark.parametrize("pair,expected", sorted(KNOWN.items()))
def test_resolve_known_pairs(pair: tuple[int, int], expected: tuple[str, str]) -> None:
    assert CONFIG.resolve(*pair) == expected


def test_resolve_unknown_class_is_none() -> None:
    assert CONFIG.resolve(-1, 0) is None
