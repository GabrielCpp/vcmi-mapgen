"""The zone economy: the mines every map must cover, the map-level mine ledger, and the
dwellings tied to a zone's town."""

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose

# the six basic resource mines every map must cover (gold is the deliberate exception:
# only worth placing when the map holds several towns)
BASIC_MINE_RES = ("sawmill", "orePit", "alchemistLab", "sulfurDune", "crystalCavern", "gemPond")

ECONOMY: tuple[str, ...] = ("sawmill", "orePit")


@dataclass(slots=True)
class Ledger:
    missing: set[str]
    towns: int
    gold: int


def mine_variants(ids: list[Identity], mine_w: Mapping[str, int]) -> list[Identity]:
    """Terrain-faithful sprite variants: mine DEFs carry a baked-in terrain apron
    (avmgogr0 grass vs avmgold0 dirt), so keep only the variants mapmakers actually
    use on THIS terrain (>= 20% of the top variant's corpus weight — drops the rare
    cross-terrain leakage that put dirt-apron mines on grass)."""
    ws = {i.animation.lower(): mine_w.get(i.animation.lower(), 0) for i in ids}
    top = max(ws.values(), default=0)
    if top > 0:
        keep = [i for i in ids if ws[i.animation.lower()] >= 0.2 * top]
        return keep or ids
    return ids


def rest_mines(
    mines: Mapping[str, list[Identity]], used_res: AbstractSet[str], ledger: Ledger | None
) -> dict[str, list[Identity]]:
    gold_ok = ledger is None or ledger.gold < max(0, ledger.towns - 1)
    return {
        res: ids
        for res, ids in mines.items()
        if res not in used_res
        and ids
        and res not in ("abandoned", "mine")  # both abandoned-mine variants
        and (res != "goldMine" or gold_ok)
    }


def tie_dwellings(objs: Iterable[PlacedObject]) -> None:
    # tie the zone's RANDOM dwellings to its town: VCMI's `sameAsTown` link makes the
    # dwelling resolve to the town's (lobby-picked) faction at game start, so the creatures
    # around a random town are its own. Instance names are minted only at export, so the
    # marker carries the town's coordinates; `vcmi.export.build_document` swaps
    # in the instanceName.
    town = next((o for o in objs if o.purpose == Purpose.TOWN), None)
    if town is not None:
        for o in objs:
            if (o.type or "").startswith("randomDwelling"):
                if o.options is None:
                    o.options = {}
                o.options["sameAsTown"] = [town.x, town.y, town.level]
