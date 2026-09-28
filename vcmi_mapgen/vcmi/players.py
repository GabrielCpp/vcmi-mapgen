"""Player slots, teams and victory conditions on a VmapDocument's header."""

from collections import defaultdict

from vcmi_mapgen.core.model import JsonValue, PlacedObject
from vcmi_mapgen.vcmi.formats import vmap as VM


def main_town(t: PlacedObject) -> dict[str, JsonValue]:
    return {
        "generateHero": True,
        "l": t.level,
        "x": t.x - 2,
        "y": t.y - 2,
    }


def parse_teams(spec: str, n: int) -> list[int]:
    """Team list from a spec string: 'ffa', '2v2', '1v3', or '0,0,1,1'."""
    if not spec or spec == "ffa":
        return list(range(n))
    if "v" in spec:
        sizes = [int(s) for s in spec.split("v")]
        if sum(sizes) != n:
            raise ValueError(f"teams {spec!r} sums to {sum(sizes)}, but players={n}")
        return [ti for ti, s in enumerate(sizes) for _ in range(s)]
    out = [int(s) for s in spec.split(",")]
    if len(out) != n:
        raise ValueError(f"teams {spec!r} lists {len(out)} ids, but players={n}")
    return out


def apply_playability(
    doc: VM.VmapDocument, player_towns: list[PlacedObject], teams: list[int]
) -> None:
    """Deterministic playability overlay on a VmapDocument (in place):

    1. exactly len(player_towns) playable slots, slot i wired to its designated town
       (any faction allowed — the towns are usually randomTown) — AND the town OBJECT
       itself gets `options.owner = <player>` (the header's mainTown alone does NOT
       assign ownership; without the owner the town stays neutral),
    2. the team matrix (`teams[i]` = team id of player i; VCMI allies equal ids),
    3. victory = DEFEAT ALL (the canonical standardWin triggered event; standardDefeat =
       7 days without town), any special victory conditions stripped.
    """
    # doc.players is already sorted by color (fm_to_document's determinism guarantee).
    for i, pl in enumerate(doc.players):
        if i < len(player_towns):
            t = player_towns[i]
            pl.main_town = main_town(t)
            pl.can_play = "PlayerOrAI"
            pl.team = int(teams[i])
            if t.type == "town":
                # concrete start town (spare-neutral top-up): the lobby must not offer
                # factions the map cannot honour — restrict to the authored one, exactly
                # like VCMI's own RMG maps do
                pl.allowed_factions = {"anyOf": [f"core:{t.subtype}"]}
                pl.random_faction = None
            else:
                # randomTown start: any faction; VCMI resolves the OWNED random town to
                # the lobby pick (CGTownInstance::randomizeFaction). PlayerInfo::defaultCastle()
                # only returns RANDOM when isFactionRandom is set — an absent/permissive
                # allowedFactions alone still defaults the lobby dropdown to the first
                # faction (Castle) sorted by id. Field name from MapFormatJson.cpp's
                # serializePlayerInfo: handler.serializeBool("randomFaction", ...).
                pl.allowed_factions = None
                pl.random_faction = True
            for vo in doc.objects:  # ownership lives on the town object
                if (
                    vo.x == t.x
                    and vo.y == t.y
                    and vo.level == t.level
                    and vo.type in ("town", "randomTown")
                ):
                    vo.options = dict(vo.options or {})
                    vo.options["owner"] = pl.id
                    break
        else:
            pl.main_town = None
            pl.can_play = "false"
            pl.team = None
    # VCMI's lobby/map-select screen reads alliances from this top-level grouping —
    # not from each player's individual "team" int above — so it must be set for
    # the UI to show teams at all. Real VCMI RMG maps omit the key entirely for FFA.
    groups: defaultdict[int, list[str]] = defaultdict(list)
    for i, pl in enumerate(doc.players[: len(player_towns)]):
        groups[int(teams[i])].append(pl.id)
    allied = [members for members in groups.values() if len(members) > 1]
    doc.teams = allied if allied else None

    MSG: dict[str, JsonValue] = {
        "exactStrings": None,
        "localStrings": None,
        "message": [2],
        "numbers": None,
    }
    doc.triggered_events = {
        "standardVictory": {
            "condition": ["standardWin", {"type": "", "value": -1}],
            "effect": {
                "messageToSend": {
                    "exactStrings": None,
                    "localStrings": None,
                    "message": None,
                    "numbers": None,
                    "stringsTextID": None,
                },
                "type": "victory",
            },
            "message": dict(MSG, stringsTextID=["core.genrltxt.659"]),
        },
        "standardDefeat": {
            "condition": ["daysWithoutTown", {"type": "", "value": 7}],
            "effect": {
                "messageToSend": {
                    "exactStrings": None,
                    "localStrings": None,
                    "message": None,
                    "numbers": None,
                    "stringsTextID": None,
                },
                "type": "defeat",
            },
            "message": dict(MSG, stringsTextID=["core.genrltxt.7"]),
        },
    }
    doc.victory_icon_index = 11  # "defeat all enemies"
    doc.victory_message = dict(MSG, stringsTextID=["core.vcdesc.0"])
    doc.defeat_icon_index = 3
    doc.defeat_message = dict(MSG, stringsTextID=["core.lcdesc.0"])
