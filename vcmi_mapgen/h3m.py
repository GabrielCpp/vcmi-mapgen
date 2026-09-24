"""Dependency-free parser for Heroes of Might & Magic 3 `.h3m` map files.

Supports RoE (0x0E/14), AB (0x15/21) and SoD (0x1C/28) formats only.
HotA / WoG / CHR are intentionally not supported.

This is a faithful re-implementation of VCMI's `CMapLoaderH3M` sequential
loader (ref/MapFormatH3M.cpp + ref/MapReaderH3M.cpp + ref/MapFeaturesH3M.cpp).
The file is parsed strictly sequentially; every section must be consumed so
the cursor lands exactly at the start of the trailing zero padding at EOF.

All multi-byte integers are little-endian.
"""

from __future__ import annotations

import gzip
import os
import struct
from dataclasses import dataclass, field
from typing import final

# ---------------------------------------------------------------------------
# Map formats
# ---------------------------------------------------------------------------
ROE = 0x0E  # 14
AB = 0x15  # 21
SOD = 0x1C  # 28


@dataclass
class Features:
    """Per-version feature flags / bitset sizes (see ref/MapFeaturesH3M.cpp)."""

    level_roe: bool = True
    level_ab: bool = False
    level_sod: bool = False

    factions_bytes: int = 1
    heroes_bytes: int = 16
    artifacts_bytes: int = 16
    skills_bytes: int = 4
    resources_bytes: int = 4
    spells_bytes: int = 9
    buildings_bytes: int = 6

    factions_count: int = 8
    heroes_count: int = 128
    heroes_portraits_count: int = 130
    artifacts_count: int = 127
    resources_count: int = 7
    creatures_count: int = 118
    spells_count: int = 70
    skills_count: int = 28
    terrains_count: int = 10
    artifact_slots_count: int = 18
    buildings_count: int = 41
    roads_count: int = 3
    rivers_count: int = 4

    hero_invalid: int = 0xFF
    artifact_invalid: int = 0xFF
    creature_invalid: int = 0xFF
    spell_invalid: int = 0xFF


def features_for(fmt: int) -> Features:
    if fmt == ROE:
        return Features()
    if fmt == AB:
        f = Features()
        f.level_ab = True
        f.factions_bytes = 2
        f.factions_count = 9
        f.creatures_count = 145
        f.heroes_count = 156
        f.heroes_portraits_count = 159
        f.heroes_bytes = 20
        f.artifacts_count = 129
        f.artifacts_bytes = 17
        f.artifact_invalid = 0xFFFF
        f.creature_invalid = 0xFFFF
        return f
    if fmt == SOD:
        f = features_for(AB)
        f.level_sod = True
        f.artifacts_count = 144
        f.artifacts_bytes = 18
        f.heroes_portraits_count = 163
        f.artifact_slots_count = 19
        return f
    raise ValueError(f"Unsupported map format {fmt:#x} (only RoE/AB/SoD)")


# ---------------------------------------------------------------------------
# Object class IDs (VCMI Obj enum, canonical H3M values)
# ---------------------------------------------------------------------------
@final
class Obj:
    NO_OBJ = -1
    ABANDONED_MINE = 220
    ARTIFACT = 5
    BLACK_MARKET = 7
    BORDER_GATE = 212
    BORDERGUARD = 9
    CAMPFIRE = 12
    CORPSE = 22
    CREATURE_BANK = 16
    CREATURE_GENERATOR1 = 17
    CREATURE_GENERATOR2 = 18
    CREATURE_GENERATOR3 = 19
    CREATURE_GENERATOR4 = 20
    CRYPT = 84
    DERELICT_SHIP = 24
    DRAGON_UTOPIA = 25
    EVENT = 26
    FLOTSAM = 28
    GARRISON = 33
    GARRISON2 = 219
    GRAIL = 36
    HERO = 34
    HERO_PLACEHOLDER = 214
    HOTA_CUSTOM_OBJECT_1 = 17
    LEAN_TO = 39
    LIGHTHOUSE = 42
    MINE = 53
    MONSTER = 54
    OCEAN_BOTTLE = 59
    PANDORAS_BOX = 6
    PRISON = 62
    PYRAMID = 63
    RANDOM_ART = 64
    RANDOM_TREASURE_ART = 65
    RANDOM_MINOR_ART = 66
    RANDOM_MAJOR_ART = 67
    RANDOM_RELIC_ART = 68
    RANDOM_ART_5 = 69  # 6th random-art tier present in H3M (AVArnd4)
    RANDOM_DWELLING = 216
    RANDOM_DWELLING_LVL = 217
    RANDOM_DWELLING_FACTION = 218
    RANDOM_HERO = 70
    RANDOM_MONSTER = 71
    RANDOM_MONSTER_L1 = 72
    RANDOM_MONSTER_L2 = 73
    RANDOM_MONSTER_L3 = 74
    RANDOM_MONSTER_L4 = 75
    RANDOM_MONSTER_L5 = 162
    RANDOM_MONSTER_L6 = 163
    RANDOM_MONSTER_L7 = 164
    RANDOM_RESOURCE = 76
    RANDOM_TOWN = 77
    RESOURCE = 79
    SCHOLAR = 81
    SEA_CHEST = 82
    SEER_HUT = 83
    SHIPWRECK = 85
    SHIPWRECK_SURVIVOR = 86
    SHIPYARD = 87
    SHRINE_OF_MAGIC_INCANTATION = 88
    SHRINE_OF_MAGIC_GESTURE = 89
    SHRINE_OF_MAGIC_THOUGHT = 90
    SIGN = 91
    SPELL_SCROLL = 93
    TOWN = 98
    TREASURE_CHEST = 101
    TREE_OF_KNOWLEDGE = 102
    SUBTERRANEAN_GATE = 103
    UNIVERSITY = 104
    WAGON = 105
    WAR_MACHINE_FACTORY = 106
    WARRIORS_TOMB = 108
    WITCH_HUT = 113
    QUEST_GUARD = 215


PRIMARY_SKILLS = 4


# ---------------------------------------------------------------------------
# Low-level cursor / reader
# ---------------------------------------------------------------------------
class DesyncError(Exception):
    """Raised when a value violates an invariant that means the cursor desynced."""


@final
class Reader:
    def __init__(self, data: bytes, features: Features) -> None:
        self.d: bytes = data
        self.pos: int = 0
        self.n: int = len(data)
        self.f: Features = features

    # -- raw primitives ------------------------------------------------------
    def u8(self) -> int:
        v = self.d[self.pos]
        self.pos += 1
        return v

    def i8(self) -> int:
        v = self.d[self.pos]
        self.pos += 1
        return v - 256 if v >= 128 else v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.pos)[0]
        self.pos += 2
        return v

    def i16(self) -> int:
        v = struct.unpack_from("<h", self.d, self.pos)[0]
        self.pos += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.pos)[0]
        self.pos += 4
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.pos)[0]
        self.pos += 4
        return v

    def boolean(self) -> bool:
        return self.u8() != 0

    def skip(self, n: int) -> None:
        self.pos += n

    def skip_zero(self, n: int) -> None:
        # VCMI asserts these are zero in debug builds. We do the same so a
        # desync is caught immediately rather than propagating silently.
        chunk = self.d[self.pos : self.pos + n]
        if any(chunk):
            raise DesyncError(f"skip_zero({n}) at {self.pos}: non-zero bytes {chunk.hex()}")
        self.pos += n

    def string(self) -> bytes:
        length = self.u32()
        if length > 1_000_000:
            raise DesyncError(f"string length {length} at {self.pos - 4} too large")
        s = self.d[self.pos : self.pos + length]
        self.pos += length
        return s

    # -- typed helpers (mirror MapReaderH3M) ---------------------------------
    def artifact(self) -> int:
        v = self.u16() if self.f.level_ab else self.u8()
        return -1 if v == self.f.artifact_invalid else v

    def artifact8(self) -> int:
        v = self.u8()
        return -1 if v == 0xFF else v

    def artifact32(self) -> int:
        return self.i32()

    def hero(self) -> int:
        v = self.u8()
        return -1 if v == self.f.hero_invalid else v

    def hero_portrait(self) -> int:
        v = self.u8()
        return -1 if v == self.f.hero_invalid else v

    def creature(self) -> int:
        v = self.u16() if self.f.level_ab else self.u8()
        return -1 if v == self.f.creature_invalid else v

    def creature32(self) -> int:
        return self.u32()

    def skill(self) -> int:
        return self.u8()

    def spell(self) -> int:
        return self.u8()

    def spell16(self) -> int:
        return self.i16()

    def spell32(self) -> int:
        return self.i32()

    def resource_id(self) -> int:
        return self.i8()

    def player(self) -> int:
        return self.u8()

    def player32(self) -> int:
        return self.u32()

    def int3(self) -> tuple[int, int, int]:
        return (self.u8(), self.u8(), self.u8())

    # -- bitmasks ------------------------------------------------------------
    def bitmask(self, bytes_to_read: int) -> list[int]:
        out: list[int] = []
        for byte in range(bytes_to_read):
            mask = self.u8()
            for bit in range(8):
                if mask & (1 << bit):
                    out.append(byte * 8 + bit)
        return out

    def bitmask_factions(self) -> list[int]:
        return self.bitmask(self.f.factions_bytes)

    def bitmask_players(self) -> list[int]:
        return self.bitmask(1)

    def bitmask_resources(self) -> list[int]:
        return self.bitmask(self.f.resources_bytes)

    def bitmask_heroes(self) -> list[int]:
        return self.bitmask(self.f.heroes_bytes)

    def bitmask_artifacts(self) -> list[int]:
        return self.bitmask(self.f.artifacts_bytes)

    def bitmask_spells(self) -> list[int]:
        return self.bitmask(self.f.spells_bytes)

    def bitmask_skills(self) -> list[int]:
        return self.bitmask(self.f.skills_bytes)

    def bitmask_buildings(self) -> list[int]:
        return self.bitmask(self.f.buildings_bytes)

    def resources(self) -> list[int]:
        return [self.i32() for _ in range(self.f.resources_count)]


# ---------------------------------------------------------------------------
# Parsed structures
# ---------------------------------------------------------------------------
@dataclass
class ObjectTemplate:
    animation: str
    block_mask: bytes
    visit_mask: bytes
    allowed_terrains: int
    terrain_group: int
    obj_class: int
    obj_subclass: int
    obj_group: int
    is_overlay: int

    @property
    def blocked_count(self) -> int:
        # passability mask: bit clear == blocked tile (H3 convention). Count
        # blocked tiles across the 6x8 footprint grid.
        count = 0
        for b in self.block_mask:
            for bit in range(8):
                if not (b & (1 << bit)):
                    count += 1
        return count


@dataclass
class MapObject:
    x: int
    y: int
    level: int
    template_index: int
    obj_class: int
    obj_subclass: int
    animation: str
    footprint: int
    extra: dict[str, int] = field(default_factory=dict)


@dataclass
class Tile:
    terrain: int
    river: bool
    road: bool
    view: int = 0
    river_type: int = 0
    river_dir: int = 0
    road_type: int = 0
    road_dir: int = 0
    mirror: int = 0


@dataclass
class H3Map:
    name: str
    fmt: int
    width: int
    height: int
    two_level: bool
    players: int
    terrain: list[list[list[Tile]]] = field(default_factory=list)  # per-level list of rows of Tile
    templates: list[ObjectTemplate] = field(default_factory=list)
    objects: list[MapObject] = field(default_factory=list)
    bytes_remaining: int = 0
    remaining_all_zero: bool = True


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
@final
class H3MParser:
    def __init__(self, data: bytes) -> None:
        fmt = int(struct.unpack_from("<I", data, 0)[0])
        self.fmt: int = fmt
        self.f: Features = features_for(fmt)
        self.r: Reader = Reader(data, self.f)
        self.templates: list[ObjectTemplate] = []
        self._cur_extra: dict[str, int] = {}

    # -- public entry --------------------------------------------------------
    def parse(self, name: str) -> H3Map:
        r = self.r
        f = self.f

        _ = r.u32()  # format version (already consumed conceptually)
        _ = r.boolean()  # any_players
        size = r.i32()
        two_level = r.boolean()
        _ = r.string()  # name
        _ = r.string()  # description
        _ = r.i8()  # difficulty
        if f.level_ab:
            _ = r.u8()  # levelLimit

        player_count = self._read_players()
        self._read_victory_loss()
        self._read_teams()
        self._read_allowed_heroes()
        self._read_disposed_heroes()
        self._read_map_options()
        self._read_allowed_artifacts()
        self._read_allowed_spells_abilities()
        self._read_rumors()
        self._read_predefined_heroes()

        terrain = self._read_terrain(size, two_level)
        self._read_object_templates()
        objects = self._read_objects(size)
        self._read_events()

        remaining = r.n - r.pos
        tail = r.d[r.pos :]
        all_zero = not any(tail)

        m = H3Map(
            name=name,
            fmt=self.fmt,
            width=size,
            height=size,
            two_level=two_level,
            players=player_count,
            terrain=terrain,
            templates=self.templates,
            objects=objects,
            bytes_remaining=remaining,
            remaining_all_zero=all_zero,
        )
        return m

    # -- header sub-sections -------------------------------------------------
    def _read_players(self) -> int:
        r, f = self.r, self.f
        count = 0
        for _ in range(8):
            can_human = r.boolean()
            can_comp = r.boolean()
            if not (can_human or can_comp):
                if f.level_roe:
                    r.skip(6)
                if f.level_ab:
                    r.skip(6)
                if f.level_sod:
                    r.skip(1)
                continue
            count += 1
            _ = r.i8()  # aiTactic
            if f.level_sod:
                r.skip(1)  # faction selectable
            _ = r.bitmask_factions()
            _ = r.boolean()  # isFactionRandom
            has_main_town = r.boolean()
            if has_main_town:
                if f.level_ab:
                    _ = r.boolean()  # generateHeroAtMainTown
                    r.skip(1)  # starting town type
                _ = r.int3()  # posOfMainTown
            _ = r.boolean()  # hasRandomHero
            main_hero = r.hero()
            if main_hero != -1:
                _ = r.hero_portrait()
                _ = r.string()  # hero name
            if f.level_ab:
                r.skip(1)
                hero_count = r.u32()
                for _ in range(hero_count):
                    _ = r.hero()
                    _ = r.string()
        return count

    def _read_victory_loss(self) -> None:
        r = self.r
        # EVictoryConditionType, -1..12 ; raw byte read
        vic = r.i8()
        if vic != -1:  # not WINSTANDARD (0xFF)
            _ = r.boolean()  # allowNormalVictory
            _ = r.boolean()  # appliesToAI
            if vic == 0:  # ARTIFACT
                _ = r.artifact()
            elif vic == 1:  # GATHERTROOP
                _ = r.creature()
                _ = r.i32()
            elif vic == 2:  # GATHERRESOURCE
                _ = r.resource_id()
                _ = r.i32()
            elif vic == 3:  # BUILDCITY
                _ = r.int3()
                _ = r.i8()
                _ = r.i8()
            elif vic in {4, 5, 6, 7}:  # BUILDGRAIL
                _ = r.int3()
            elif vic in {8, 9}:  # TAKEDWELLINGS
                pass
            elif vic == 10:  # TRANSPORTITEM
                _ = r.artifact8()
                _ = r.int3()
            else:
                raise DesyncError(f"unhandled victory condition {vic}")
        loss = r.i8()
        if loss != -1:  # not LOSSSTANDARD
            if loss in {0, 1}:  # LOSSCASTLE
                _ = r.int3()
            elif loss == 2:  # TIMEEXPIRES
                _ = r.u16()
            else:
                raise DesyncError(f"unhandled loss condition {loss}")

    def _read_teams(self) -> None:
        r = self.r
        how_many = r.u8()
        if how_many > 0:
            for _ in range(8):
                _ = r.u8()

    def _read_allowed_heroes(self) -> None:
        r, f = self.r, self.f
        _ = r.bitmask_heroes()
        if f.level_ab:
            placeholders = r.u32()
            for _ in range(placeholders):
                _ = r.hero()

    def _read_disposed_heroes(self) -> None:
        r, f = self.r, self.f
        if not f.level_sod:
            return
        disp = r.u8()
        for _ in range(disp):
            _ = r.hero()
            _ = r.hero_portrait()
            _ = r.string()
            _ = r.bitmask_players()

    def _read_map_options(self) -> None:
        # 31 zero bytes (SoD/AB/RoE; HotA-only options excluded)
        self.r.skip_zero(31)

    def _read_allowed_artifacts(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            _ = r.bitmask_artifacts()

    def _read_allowed_spells_abilities(self) -> None:
        r, f = self.r, self.f
        if f.level_sod:
            _ = r.bitmask_spells()
            _ = r.bitmask_skills()

    def _read_rumors(self) -> None:
        r = self.r
        count = r.u32()
        if count > 1000:
            raise DesyncError(f"rumor count {count} too large")
        for _ in range(count):
            _ = r.string()  # name
            _ = r.string()  # text

    def _read_predefined_heroes(self) -> None:
        r, f = self.r, self.f
        if not f.level_sod:
            return
        heroes_count = f.heroes_count
        for _ in range(heroes_count):
            custom = r.boolean()
            if not custom:
                continue
            has_exp = r.boolean()
            if has_exp:
                _ = r.u32()
            has_sec = r.boolean()
            if has_sec:
                how_many = r.u32()
                for _ in range(how_many):
                    _ = r.skill()
                    _ = r.i8()
            self._read_artifacts_of_hero()
            has_bio = r.boolean()
            if has_bio:
                _ = r.string()
            _ = r.i8()  # gender
            has_spells = r.boolean()
            if has_spells:
                _ = r.bitmask_spells()
            has_prim = r.boolean()
            if has_prim:
                for _ in range(PRIMARY_SKILLS):
                    _ = r.u8()

    def _read_artifacts_of_hero(self) -> None:
        r, f = self.r, self.f
        has_set = r.boolean()
        if not has_set:
            return
        for _ in range(f.artifact_slots_count):
            _ = r.artifact()
        amount = r.u16()
        for _ in range(amount):
            _ = r.artifact()

    # -- terrain -------------------------------------------------------------
    def _read_terrain(self, size: int, two_level: bool) -> list[list[list[Tile]]]:
        r = self.r
        levels = 2 if two_level else 1
        out: list[list[list[Tile]]] = []
        for _ in range(levels):
            level_rows: list[list[Tile]] = []
            for _ in range(size):
                row: list[Tile] = []
                for _ in range(size):
                    terrain_type = r.u8()
                    ter_view = r.u8()
                    river_type = r.u8() & 0x07
                    river_dir = r.u8()
                    road_type = r.u8()
                    road_dir = r.u8()
                    mirror = r.u8()  # extTileFlags / mirroring
                    row.append(
                        Tile(
                            terrain=terrain_type,
                            river=river_type != 0,
                            road=road_type != 0,
                            view=ter_view,
                            river_type=river_type,
                            river_dir=river_dir,
                            road_type=road_type,
                            road_dir=road_dir,
                            mirror=mirror,
                        )
                    )
                level_rows.append(row)
            out.append(level_rows)
        return out

    # -- object templates ----------------------------------------------------
    def _read_object_templates(self) -> None:
        r = self.r
        count = r.u32()
        for _ in range(count):
            animation = r.string().decode("latin-1")
            block_mask = bytes(r.u8() for _ in range(6))
            visit_mask = bytes(r.u8() for _ in range(6))
            allowed_terrains = r.u16()
            terrain_group = r.u16()
            obj_class = r.u32()
            obj_subclass = r.u32()
            obj_group = r.u8()
            is_overlay = r.u8()
            r.skip_zero(16)
            self.templates.append(
                ObjectTemplate(
                    animation=animation,
                    block_mask=block_mask,
                    visit_mask=visit_mask,
                    allowed_terrains=allowed_terrains,
                    terrain_group=terrain_group,
                    obj_class=obj_class,
                    obj_subclass=obj_subclass,
                    obj_group=obj_group,
                    is_overlay=is_overlay,
                )
            )

    # -- objects -------------------------------------------------------------
    def _read_objects(self, size: int) -> list[MapObject]:
        r = self.r
        count = r.u32()
        objects: list[MapObject] = []
        for _ in range(count):
            x, y, z = r.int3()
            def_index = r.u32()
            tmpl = self.templates[def_index]
            r.skip_zero(5)
            self._cur_extra = {}
            self._read_object_body(tmpl)

            # VCMI accepts anchor positions up to size+7 (object bottom-right
            # corner of objects whose visitable tile lies off the visible grid).
            if not (0 <= x < size + 8 and 0 <= y < size + 8):
                raise DesyncError(f"object position out of range ({x},{y}) size={size}")

            objects.append(
                MapObject(
                    x=x,
                    y=y,
                    level=z,
                    template_index=def_index,
                    obj_class=tmpl.obj_class,
                    obj_subclass=tmpl.obj_subclass,
                    animation=tmpl.animation,
                    footprint=tmpl.blocked_count,
                    extra=self._cur_extra,
                )
            )
        return objects

    def _read_object_body(self, tmpl: ObjectTemplate) -> None:
        oid = tmpl.obj_class
        sub = tmpl.obj_subclass

        if oid == Obj.EVENT:
            self._read_event_obj()
        elif oid in (Obj.HERO, Obj.RANDOM_HERO, Obj.PRISON):
            self._read_hero_obj()
        elif oid in (
            Obj.MONSTER,
            Obj.RANDOM_MONSTER,
            Obj.RANDOM_MONSTER_L1,
            Obj.RANDOM_MONSTER_L2,
            Obj.RANDOM_MONSTER_L3,
            Obj.RANDOM_MONSTER_L4,
            Obj.RANDOM_MONSTER_L5,
            Obj.RANDOM_MONSTER_L6,
            Obj.RANDOM_MONSTER_L7,
        ):
            self._read_monster()
        elif oid in (Obj.OCEAN_BOTTLE, Obj.SIGN):
            self._read_sign()
        elif oid == Obj.SEER_HUT:
            self._read_seer_hut()
        elif oid == Obj.WITCH_HUT:
            self._read_witch_hut()
        elif oid == Obj.SCHOLAR:
            self._read_scholar()
        elif oid in (Obj.GARRISON, Obj.GARRISON2):
            self._read_garrison()
        elif oid == Obj.ARTIFACT or 65 <= oid <= 69:
            # ARTIFACT(5) and the five random-artifact tiers (65..69).
            # Class 64 (RANDOM_ART placeholder) carries no body.
            self._read_artifact_obj()
        elif oid == Obj.SPELL_SCROLL:
            self._read_scroll()
        elif oid in (Obj.RANDOM_RESOURCE, Obj.RESOURCE):
            self._read_resource()
        elif oid in (Obj.RANDOM_TOWN, Obj.TOWN):
            self._read_town()
        elif oid in (Obj.MINE, Obj.ABANDONED_MINE):
            if sub < 7:
                self._read_mine()
            else:
                self._read_abandoned_mine()
        elif oid in (
            Obj.CREATURE_GENERATOR1,
            Obj.CREATURE_GENERATOR2,
            Obj.CREATURE_GENERATOR3,
            Obj.CREATURE_GENERATOR4,
        ):
            self._read_dwelling()
        elif oid in (
            Obj.SHRINE_OF_MAGIC_INCANTATION,
            Obj.SHRINE_OF_MAGIC_GESTURE,
            Obj.SHRINE_OF_MAGIC_THOUGHT,
        ):
            self._read_shrine()
        elif oid == Obj.PANDORAS_BOX:
            self._read_pandora()
        elif oid == Obj.GRAIL:
            self._read_grail()
        elif oid in (
            Obj.RANDOM_DWELLING,
            Obj.RANDOM_DWELLING_LVL,
            Obj.RANDOM_DWELLING_FACTION,
        ):
            self._read_dwelling_random(tmpl)
        elif oid == Obj.QUEST_GUARD:
            self._read_quest_guard()
        elif oid == Obj.SHIPYARD:
            self._read_shipyard()
        elif oid == Obj.HERO_PLACEHOLDER:
            self._read_hero_placeholder()
        elif oid == Obj.LIGHTHOUSE:
            self._read_lighthouse()
        elif oid in (
            Obj.CREATURE_BANK,
            Obj.DERELICT_SHIP,
            Obj.DRAGON_UTOPIA,
            Obj.CRYPT,
            Obj.SHIPWRECK,
        ):
            self._read_bank()
        elif oid == Obj.BORDER_GATE:
            # HotA hacks (sub 1000/1001) excluded; plain generic body for SoD
            pass
        else:
            # Generic object: no type-specific body in RoE/AB/SoD.
            pass

    # ----- object body readers ----------------------------------------------
    def _read_message_and_guards(self) -> None:
        r = self.r
        has_message = r.boolean()
        if has_message:
            _ = r.string()
            has_guards = r.boolean()
            if has_guards:
                self._read_creature_set()
            r.skip_zero(4)

    def _read_creature_set(self) -> None:
        r = self.r
        for _ in range(7):
            _ = r.creature()
            _ = r.u16()

    def _read_box_content(self) -> None:
        r = self.r
        self._read_message_and_guards()
        _ = r.u32()  # heroExperience
        _ = r.i32()  # manaDiff
        _ = r.i8()  # morale
        _ = r.i8()  # luck
        _ = r.resources()
        for _ in range(PRIMARY_SKILLS):
            _ = r.u8()
        gabn = r.u8()
        for _ in range(gabn):
            _ = r.skill()
            _ = r.i8()
        gart = r.u8()
        for _ in range(gart):
            _ = r.artifact()
        gspel = r.u8()
        for _ in range(gspel):
            _ = r.spell()
        gcre = r.u8()
        for _ in range(gcre):
            _ = r.creature()
            _ = r.u16()
        r.skip_zero(8)

    def _read_event_obj(self) -> None:
        r = self.r
        self._read_box_content()
        _ = r.bitmask_players()
        _ = r.boolean()  # computerActivate
        _ = r.boolean()  # removeAfterVisit
        r.skip_zero(4)
        # humanActivate present only for HOTA3 -> skipped

    def _read_pandora(self) -> None:
        self._read_box_content()

    def _read_monster(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            _ = r.u32()  # quest identifier
        self._cur_extra["count"] = r.u16()  # stack size (guard strength)
        self._cur_extra["character"] = r.i8()  # aggression: 0 compliant .. 4 savage
        has_message = r.boolean()
        if has_message:
            _ = r.string()
            _ = r.resources()
            _ = r.artifact()  # gained artifact
        _ = r.boolean()  # neverFlees
        _ = r.boolean()  # notGrowingTeam
        r.skip_zero(2)

    def _read_sign(self) -> None:
        r = self.r
        _ = r.string()
        r.skip_zero(4)

    def _read_seer_hut(self) -> None:
        r = self.r
        # questsCount == 1 for non-HotA
        self._read_seer_hut_quest()
        r.skip_zero(2)

    def _read_seer_hut_quest(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            mission_type = self._read_quest()
        else:
            art = r.artifact()
            mission_type = 1 if art != -1 else 0  # ARTIFACT or NONE

        if mission_type != 0:
            reward_type = r.i8()  # 0..10
            if reward_type == 0:  # NOTHING
                pass
            elif reward_type in {1, 2}:  # EXPERIENCE
                _ = r.u32()
            elif reward_type in {3, 4}:  # MORALE
                _ = r.i8()
            elif reward_type == 5:  # RESOURCES
                _ = r.resource_id()
                _ = r.u32()
            elif reward_type == 6:  # PRIMARY_SKILL
                _ = r.u8()
                _ = r.u8()
            elif reward_type == 7:  # SECONDARY_SKILL
                _ = r.skill()
                _ = r.i8()
            elif reward_type == 8:  # ARTIFACT
                _ = r.artifact()
            elif reward_type == 9:  # SPELL
                _ = r.spell()
            elif reward_type == 10:  # CREATURE
                _ = r.creature()
                _ = r.u16()
            else:
                raise DesyncError(f"bad seer hut reward type {reward_type}")
        else:
            r.skip_zero(1)

    def _read_quest(self) -> int:
        """Reads a quest (AB+). Returns the mission id (post-resolution)."""
        r = self.r
        mission = r.i8()  # 0..10
        if mission == 0:  # NONE
            return mission
        elif mission == 1:  # PRIMARY_SKILL (level? -> 4 bytes)
            for _ in range(4):
                _ = r.u8()
        elif mission == 2 or mission in (3, 4):  # LEVEL
            _ = r.u32()
        elif mission == 5:  # ARTIFACT
            art_number = r.u8()
            for _ in range(art_number):
                _ = r.artifact()
        elif mission == 6:  # ARMY
            type_number = r.u8()
            for _ in range(type_number):
                _ = r.creature()
                _ = r.u16()
        elif mission == 7:  # RESOURCES
            for _ in range(7):
                _ = r.u32()
        elif mission == 8:  # HERO
            _ = r.hero()
        elif mission == 9:  # PLAYER
            _ = r.player()
        else:
            raise DesyncError(f"bad quest mission {mission}")
        _ = r.i32()  # lastDay
        _ = r.string()  # firstVisit
        _ = r.string()  # nextVisit
        _ = r.string()  # completed
        return mission

    def _read_witch_hut(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            _ = r.bitmask_skills()

    def _read_scholar(self) -> None:
        r = self.r
        _ = r.i8()  # bonus type
        _ = r.u8()  # bonus id
        r.skip_zero(6)

    def _read_garrison(self) -> None:
        r, f = self.r, self.f
        _ = r.player32()
        self._read_creature_set()
        if f.level_ab:
            _ = r.boolean()  # removableUnits
        r.skip_zero(8)

    def _read_artifact_obj(self) -> None:
        self._read_message_and_guards()

    def _read_scroll(self) -> None:
        r = self.r
        self._read_message_and_guards()
        _ = r.spell32()

    def _read_resource(self) -> None:
        r = self.r
        self._read_message_and_guards()
        _ = r.u32()  # amount
        r.skip_zero(4)

    def _read_mine(self) -> None:
        self._cur_extra["owner"] = self.r.player32()

    def _read_abandoned_mine(self) -> None:
        _ = self.r.bitmask_resources()

    def _read_dwelling(self) -> None:
        self._cur_extra["owner"] = self.r.player32()

    def _read_dwelling_random(self, tmpl: ObjectTemplate) -> None:
        r = self.r
        _ = r.player32()
        oid = tmpl.obj_class
        has_faction = oid in (Obj.RANDOM_DWELLING, Obj.RANDOM_DWELLING_LVL)
        has_level = oid in (Obj.RANDOM_DWELLING, Obj.RANDOM_DWELLING_FACTION)
        if has_faction:
            identifier = r.u32()
            if identifier == 0:
                _ = r.bitmask_factions()
        if has_level:
            _ = r.u8()  # minLevel
            _ = r.u8()  # maxLevel

    def _read_shrine(self) -> None:
        _ = self.r.spell32()

    def _read_grail(self) -> None:
        _ = self.r.i32()  # radius

    def _read_quest_guard(self) -> None:
        _ = self._read_quest()

    def _read_shipyard(self) -> None:
        _ = self.r.player32()

    def _read_hero_placeholder(self) -> None:
        r = self.r
        _ = r.player()
        if r.hero() == -1:
            _ = r.u8()

    def _read_lighthouse(self) -> None:
        _ = self.r.player32()

    def _read_bank(self) -> None:
        # HotA3+ adds settings; not present in RoE/AB/SoD.
        pass

    def _read_hero_obj(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            _ = r.u32()  # quest identifier
        self._cur_extra["owner"] = r.player()  # owner
        _ = r.hero()  # hero type
        has_name = r.boolean()
        if has_name:
            _ = r.string()
        if f.level_sod:
            has_exp = r.boolean()
            if has_exp:
                _ = r.u32()
        else:
            _ = r.u32()  # exp always present
        has_portrait = r.boolean()
        if has_portrait:
            _ = r.hero_portrait()
        has_sec = r.boolean()
        if has_sec:
            n = r.u32()
            for _ in range(n):
                _ = r.skill()
                _ = r.i8()
        has_garrison = r.boolean()
        if has_garrison:
            self._read_creature_set()
        _ = r.i8()  # formation
        self._read_artifacts_of_hero()
        _ = r.u8()  # patrol radius
        if f.level_ab:
            has_bio = r.boolean()
            if has_bio:
                _ = r.string()
            _ = r.i8()  # gender
        if f.level_sod:
            has_spells = r.boolean()
            if has_spells:
                _ = r.bitmask_spells()
        elif f.level_ab:
            _ = r.spell()  # single spell
        if f.level_sod:
            has_prim = r.boolean()
            if has_prim:
                for _ in range(PRIMARY_SKILLS):
                    _ = r.u8()
        r.skip_zero(16)

    def _read_town(self) -> None:
        r, f = self.r, self.f
        if f.level_ab:
            _ = r.u32()  # identifier
        self._cur_extra["owner"] = r.player()  # owner (255 = neutral)
        has_name = r.boolean()
        if has_name:
            _ = r.string()
        has_garrison = r.boolean()
        if has_garrison:
            self._read_creature_set()
        _ = r.i8()  # formation
        has_custom_buildings = r.boolean()
        if has_custom_buildings:
            _ = r.bitmask_buildings()  # built
            _ = r.bitmask_buildings()  # forbidden
        else:
            _ = r.boolean()  # hasFort
        if f.level_ab:
            _ = r.bitmask_spells()  # obligatory spells
        _ = r.bitmask_spells()  # possible spells
        # spellResearchAllowed only HOTA1+, skipped
        events_count = r.u32()
        for _ in range(events_count):
            self._read_event_common()
            _ = r.bitmask_buildings()  # new buildings
            for _ in range(7):
                _ = r.u16()  # creatures
            r.skip_zero(4)
        if f.level_sod:
            _ = r.u8()  # alignment
        r.skip_zero(3)

    def _read_event_common(self) -> None:
        r, f = self.r, self.f
        _ = r.string()  # name
        _ = r.string()  # message
        _ = r.resources()
        _ = r.bitmask_players()
        if f.level_sod:
            _ = r.boolean()  # humanAffected
        _ = r.boolean()  # computerAffected
        _ = r.u16()  # firstOccurrence
        _ = r.u16()  # nextOccurrence
        r.skip_zero(16)

    def _read_events(self) -> None:
        r = self.r
        count = r.u32()
        for _ in range(count):
            self._read_event_common()


def parse_file(path: str) -> H3Map:
    with open(path, "rb") as fh:
        raw = fh.read()
    data = gzip.decompress(raw)
    name = os.path.splitext(os.path.basename(path))[0]
    return H3MParser(data).parse(name)
