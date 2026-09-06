"""The identity-rebuild engine: per-zone templates in a shape-relative frame, bit-exact
same-shape replay (pure integer math — the identity guarantee), and rough different-shape
warp adaptation of a zone's objects onto a deformed target."""
import collections
import glob
import hashlib
import json
import os
import statistics

import numpy as np

from vcmi_mapgen.kit import terrain_segment as TS
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import vmap as VM
from vcmi_mapgen.kit.segmentation import _segment_level
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.kit.paths import project_root, slug, vcmi_home
from vcmi_mapgen.kit.tiling import _cell

ROOT = project_root()


def slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def zone_bbox_mask(tiles):
    """(minx,miny,maxx,maxy), sorted bbox-relative tile list. Order-independent."""
    xs = [x for x, y in tiles]
    ys = [y for x, y in tiles]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    mask_rel = sorted((x - minx, y - miny) for x, y in tiles)
    return (minx, miny, maxx, maxy), mask_rel

def label_zone(zone, objs_in, W, H):
    """Deterministic human label: terrain + dominant gameplay purpose + map octant."""
    terr = TNAME.get(zone["terrain_type"], f"t{zone['terrain_type']}")
    purps = [OR.purpose_of(o) for o in objs_in]
    purps = [p for p in purps if p not in ("DECORATION", "UNKNOWN")]
    if purps:
        c = collections.Counter(purps)
        top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    else:
        top = "EMPTY"
    cx, cy = zone["centroid"]
    ns = "N" if cy < H / 3 else ("S" if cy > 2 * H / 3 else "")
    ew = "W" if cx < W / 3 else ("E" if cx > 2 * W / 3 else "")
    return f"{terr}-{top}-{(ns + ew) or 'C'}"


# ---------------------------------------------------------------------------
# Extraction:  map -> template
# ---------------------------------------------------------------------------

def _bucket_objects(objects, level, zone_label, zones, W, H):
    """Split this level's objects into per-zone buckets + a barrier bucket.

    An object whose ANCHOR sits in a zone belongs to that zone (unchanged). An object
    anchored OFF every zone (on water/rock) but whose FOOTPRINT overlaps a zone — e.g.
    a rim mountain anchored on the surrounding rock — is a boundary object that belongs
    to the zone it touches most (deterministic, smallest-zone-id tie-break), so the
    patch keeps its full rim. Each object still lands in exactly one bucket, so the
    bit-exact identity rebuild is preserved (same object, same absolute position)."""
    zone_objs = {zid: [] for zid in zones}
    barrier = []
    for o in objects:
        if o.get("l", 0) != level:
            continue
        x, y = o["x"], o["y"]
        z = zone_label[y][x] if (0 <= x < W and 0 <= y < H) else -1
        if z >= 0 and z in zones:
            zone_objs[z].append(o)
            continue
        cover = collections.Counter()
        for tx, ty, _blk in OR.mask_cells(o["mask"], x, y):
            if 0 <= tx < W and 0 <= ty < H:
                zz = zone_label[ty][tx]
                if zz >= 0 and zz in zones:
                    cover[zz] += 1
        if cover:
            zone_objs[max(sorted(cover), key=lambda zid: cover[zid])].append(o)
        else:
            barrier.append(o)
    return zone_objs, barrier

def extract_template(name: str) -> dict:
    fm = OR.load_faithful(name)
    W, H = fm["width"], fm["height"]
    levels_out = []
    for L, lvl in enumerate(fm["terrain"]):
        zones, zone_label, canon = _segment_level(lvl)
        zone_objs, barrier = _bucket_objects(fm["objects"], L, zone_label, zones, W, H)

        zones_out = []
        for zid in sorted(zones):
            z = zones[zid]
            bbox, mask_rel = zone_bbox_mask(z["tiles"])
            minx, miny = bbox[0], bbox[1]
            cz = canon[zid]
            objl = []
            for o in zone_objs[zid]:
                if (o["x"], o["y"]) in cz:
                    cd, cs = cz[(o["x"], o["y"])]
                else:                       # boundary object anchored off-zone: use the
                    ft = [(tx, ty) for tx, ty, _b in OR.mask_cells(o["mask"], o["x"], o["y"])
                          if (tx, ty) in cz]   # footprint tile nearest the anchor
                    if ft:
                        bx, by = min(ft, key=lambda t: (t[0] - o["x"]) ** 2 + (t[1] - o["y"]) ** 2)
                        cd, cs = cz[(bx, by)]
                    else:
                        cd, cs = 0.0, 0.0
                objl.append({
                    "purpose": OR.purpose_of(o),
                    "identity": OR.exact_identity(o),
                    "anchor_off": [o["x"] - minx, o["y"] - miny],
                    "canon": [round(cd, 6), round(cs, 6)],
                })
            objl.sort(key=lambda e: (e["anchor_off"][1], e["anchor_off"][0],
                                     e["identity"]["type"], e["identity"]["subtype"]))
            mask_rel_l = [[dx, dy] for (dx, dy) in mask_rel]
            zones_out.append({
                "zone_id": zid,
                "terrain_type": z["terrain_type"],
                "area": z["area"],
                "bbox": list(bbox),
                "centroid": [round(z["centroid"][0], 3), round(z["centroid"][1], 3)],
                "label": label_zone(z, zone_objs[zid], W, H),
                "shape_hash": hashlib.sha1(repr(mask_rel_l).encode()).hexdigest()[:12],
                "mask_rel": mask_rel_l,
                "objects": objl,
            })

        barrier_out = [{"purpose": OR.purpose_of(o), "identity": OR.exact_identity(o),
                        "x": o["x"], "y": o["y"]}
                       for o in sorted(barrier, key=lambda o: (o["y"], o["x"], o["type"]))]
        levels_out.append({"level": L, "zones": zones_out, "barrier_objects": barrier_out})

    return {
        "name": fm["name"], "width": W, "height": H,
        "twoLevel": fm.get("twoLevel", len(fm["terrain"]) > 1),
        "players": fm.get("players", 1),
        "levels": levels_out,
    }

def write_template(name: str, out: str | None = None):
    t = extract_template(name)
    out = out or os.path.join(ROOT, "out", f"zone_template-{slug(name)}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(t, open(out, "w"))
    return out, t


# ---------------------------------------------------------------------------
# Whole-map rebuild:  template + target terrain -> objects
# ---------------------------------------------------------------------------

def rebuild_map(template: dict, target_terrain: list, identity: bool = False):
    """Whole-map rebuild via per-zone shape matching (identity short-circuit).

    Each template zone is matched to the target zone with the SAME (mask_rel, bbox)
    and its objects replayed at bbox_min + anchor_off (pure integer => bit-exact when
    target == source). Barrier-bucket objects are replayed at absolute coords.
    """
    objects = []
    stats = {"identity": 0, "missing": 0}
    for lvl_entry in template["levels"]:
        L = lvl_entry["level"]
        if L >= len(target_terrain):
            continue
        zones_t, _ = TS.segment(target_terrain[L])
        index = {}
        for zid, z in zones_t.items():
            bbox, mask_rel = zone_bbox_mask(z["tiles"])
            index[(tuple(mask_rel), bbox)] = bbox
        for ztmpl in lvl_entry["zones"]:
            key = (tuple((dx, dy) for dx, dy in ztmpl["mask_rel"]), tuple(ztmpl["bbox"]))
            bbox = index.get(key)
            if bbox is None:
                stats["missing"] += 1
                continue
            minx, miny = bbox[0], bbox[1]
            for obj in ztmpl["objects"]:
                objects.append({**obj["identity"],
                                "x": minx + obj["anchor_off"][0],
                                "y": miny + obj["anchor_off"][1], "l": L})
            stats["identity"] += 1
        for bo in lvl_entry["barrier_objects"]:
            objects.append({**bo["identity"], "x": bo["x"], "y": bo["y"], "l": L})

    fm = {"name": template["name"], "width": template["width"], "height": template["height"],
          "twoLevel": template.get("twoLevel", False), "players": template.get("players", 1),
          "terrain": target_terrain, "objects": objects}
    return fm, stats

def _default_header() -> dict:
    """A real RMG-produced .vmap header if a local VCMI install has one (richer fidelity
    -- rumors, difficulty, description, ... -- preserved via VmapDocument.extra), else
    the static template."""
    rmg = glob.glob(os.path.join(vcmi_home(), "Maps", "RandomMaps", "*.vmap"))
    if rmg:
        return VM.read_header(rmg[0])
    tpl = str(ROOT / "data" / "vmap_header_template.json")
    return json.load(open(tpl))


def fm_to_document(fm: dict, name: str | None = None):
    """A rebuilt/generated faithful-shaped dict -> a full, writable VmapDocument.

    Mirrors the retired faithful.to_vmap: builds each object's VCMI-charset mask/
    visitableFrom, resolves `options["sameAsTown"]` markers ([x,y,l]) to the real
    town's instanceName, and wires each player slot to its own starting town
    (fm["main_town"] goes to player 0) so the map is actually playable.
    """
    terrain = [[[VM.tile_string(c) for c in row] for row in lvl] for lvl in fm["terrain"]]

    objects = []
    for o in fm["objects"]:
        if not o.get("type"):
            continue
        mask = VM.export_mask(o)
        vf = o.get("visitableFrom") or VM.visitable_from(o["mask"])
        objects.append(VM.VmapObject(
            instance_name="", type=o["type"], subtype=o["subtype"], l=o["l"],
            x=o["x"], y=o["y"], animation=o["animation"], mask=mask,
            visitable_from=vf, options=dict(o["options"]) if o.get("options") else None,
        ))
    for n, vo in enumerate(objects, 1):
        vo.instance_name = f"{vo.type}_{n}"

    # dwelling->town faction links: the generator marks `sameAsTown` with the town's
    # [x, y, l] (instance names are minted only here, above); VCMI wants the town's
    # instanceName. A marker whose town vanished is dropped (dwelling stays any-faction).
    town_names = {(vo.x, vo.y, vo.l): vo.instance_name
                  for vo in objects if vo.type in ("town", "randomTown")}
    for vo in objects:
        tag = (vo.options or {}).get("sameAsTown")
        if isinstance(tag, list):
            town_name = town_names.get(tuple(tag))
            if town_name:
                vo.options["sameAsTown"] = town_name
            else:
                del vo.options["sameAsTown"]
                if not vo.options:
                    vo.options = None

    doc = VM.VmapDocument(
        name=name or fm.get("name", "generated"),
        width=fm["width"], height=fm["height"],
        two_level=fm.get("twoLevel", len(fm["terrain"]) > 1),
        terrain=terrain, objects=objects,
        **VM.header_fields(_default_header()),
    )
    # Deterministic regardless of the header source's own key order (a real RMG header's
    # dict order isn't guaranteed alphabetical; the template's happens to be, but replay
    # must not depend on that coincidence -- see AGENTS.md's determinism rule).
    doc.players.sort(key=lambda p: p.id)

    # Wire EACH player slot to its own starting town so the map is actually playable.
    # VCMI links a player to a town via mainTown = town_anchor - (2,2); the town object
    # itself stays owner=None. Surface towns first, then put the start town
    # (fm["main_town"]) on player 0.
    towns = [o for o in fm["objects"] if OR.type_to_purpose(o.get("type")) == "TOWN"]
    towns.sort(key=lambda o: (o.get("l", 0), o["y"], o["x"]))
    mt = fm.get("main_town")
    if mt is not None:  # start town first => player 0
        towns.sort(key=lambda o: not (o.get("l", 0) == mt["l"]
                                      and o["x"] - 2 == mt["x"] and o["y"] - 2 == mt["y"]))
    for i, pl in enumerate(doc.players):
        if i < len(towns):
            t = towns[i]
            pl.main_town = {"generateHero": True, "l": t.get("l", 0),
                            "x": t["x"] - 2, "y": t["y"] - 2}
            pl.can_play = "PlayerOrAI"
        else:
            pl.main_town = None
            pl.can_play = "false"
    return doc


def rebuild_zone_warp(ztmpl: dict, target_zone: dict, target_canon: dict, level: int):
    """Rough different-shape warp of one template zone onto one target zone.

    Each source object goes to the free target tile nearest in (depth,sweep) canonical
    space whose BLOCKING footprint stays inside the zone (decoration spill tolerated).
    """
    tiles = sorted(target_zone["tiles"], key=lambda t: (t[1], t[0]))  # stable tie-break
    arr = np.array([target_canon[(x, y)] for (x, y) in tiles], dtype=np.float64)
    tiles_set = target_zone["tiles_set"]
    used, placed, dropped = set(), [], 0
    for obj in ztmpl["objects"]:
        cd, cs = obj["canon"]
        order = np.argsort((arr[:, 0] - cd) ** 2 + (arr[:, 1] - cs) ** 2, kind="stable")
        chosen = None
        for idx in order:
            x, y = tiles[int(idx)]
            if (x, y) in used:
                continue
            if all((tx, ty) in tiles_set
                   for tx, ty, blk in OR.mask_cells(obj["identity"]["mask"], x, y) if blk):
                chosen = (x, y)
                break
        if chosen is None:
            dropped += 1
            continue
        used.add(chosen)
        placed.append({**obj["identity"], "x": chosen[0], "y": chosen[1], "l": level})
    return placed, {"placed": len(placed), "dropped": dropped, "src": len(ztmpl["objects"])}

def verify_identity(name: str, fm: dict):
    """Multiset-compare rebuilt objects to the source faithful map (all levels)."""
    src = OR.load_faithful(name)

    def k(o):
        return (o["x"], o["y"], o["l"], o.get("type"), o.get("subtype"),
                o.get("animation"), tuple(o["mask"]))

    cs = collections.Counter(k(o) for o in src["objects"])
    cr = collections.Counter(k(o) for o in fm["objects"])
    matched = sum((cs & cr).values())
    missing, extra = cs - cr, cr - cs
    return (not missing and not extra), sum(cs.values()), matched, missing, extra


# ---------------------------------------------------------------------------
# Feature understanding (rules-as-code): summarize each zone into a feature profile
# (per-purpose density + where-in-the-shape it sits + which concrete objects it uses).
# ---------------------------------------------------------------------------

# Placement priority: anchors and large gameplay first, decoration (the walls) last.
_PRIORITY = {"TOWN": 0, "BANK": 1, "DWELLING": 2, "QUEST_GATE": 3, "MINE": 4,
             "TRANSPORT": 5, "WATER_TRANSPORT": 5, "STAT_PERMANENT": 6, "SPELL_SKILL": 6,
             "BONUS_TEMP": 6, "MANA": 6, "INFO": 7, "TERRAIN_MODIFIER": 7,
             "RESOURCE_PILE": 8, "REWARD_PICKUP": 9, "GUARD": 10, "DECORATION": 99}

def _prio(p):
    return _PRIORITY.get(p, 50)

def _obj_canon(o, canon_zone, tiles_set):
    """Shape-intrinsic (depth, sweep) for an object: the RIM-MOST zone tile its
    footprint overlaps (min depth). A boundary object may be anchored OUTSIDE the
    zone (on neighbour/rock tiles) — e.g. a rim mountain gathered by footprint
    overlap in `_bucket_objects` — so anchor-canon alone would miss it; overlap-canon
    classifies it as the rim (depth~0) instead. Falls back to the anchor tile's own
    canon, then (0.0, 0.0), for an object with no footprint tile in the zone at all."""
    best = None
    for tx, ty, _ in OR.mask_cells(o["mask"], o["x"], o["y"]):
        if (tx, ty) in tiles_set:
            d, s = canon_zone[(tx, ty)]
            if best is None or d < best[0]:
                best = (d, s)
    if best is not None:
        return best
    if (o["x"], o["y"]) in canon_zone:
        return canon_zone[(o["x"], o["y"])]
    return (0.0, 0.0)


def zone_features(zone, objs, canon_zone):
    """Summarize ONE zone into a feature profile (the 'understanding').

    Per purpose: count, density (per tile), depth signature (mu/sd of interior
    depth = where in the shape it sits), typical within-purpose spacing, and the
    concrete object identities it uses (so a rebuild reuses the same kinds)."""
    area = zone["area"]
    tiles_set = zone["tiles_set"]
    by_p = collections.defaultdict(list)
    for o in objs:
        d, s = _obj_canon(o, canon_zone, tiles_set)
        by_p[OR.purpose_of(o)].append((o, d, s))

    purposes = {}
    for p, items in by_p.items():
        depths = [d for _, d, _ in items]
        pts = [(o["x"], o["y"]) for o, _, _ in items]
        purposes[p] = {
            "count": len(items),
            "density": round(len(items) / area, 5),
            "depth_mu": round(statistics.fmean(depths), 4),
            "depth_sd": round(statistics.pstdev(depths) if len(depths) > 1 else 0.0, 4),
            "spacing": round(_median_nn(pts), 2),
            "identities": _dedup_identities(o for o, _, _ in items),
        }

    # guard<->reward coupling: median distance from each GUARD to nearest reward/loot.
    guards = [(o["x"], o["y"]) for o, _, _ in by_p.get("GUARD", [])]
    loot = [(o["x"], o["y"]) for pp in ("REWARD_PICKUP", "RESOURCE_PILE", "BANK")
            for o, _, _ in by_p.get(pp, [])]
    coupling = None
    if guards and loot:
        coupling = round(statistics.fmean(
            min(abs(gx - lx) + abs(gy - ly) for lx, ly in loot) for gx, gy in guards), 2)

    return {"zone_id": zone.get("_zid"), "terrain": zone["terrain_type"], "area": area,
            "guard_loot_dist": coupling, "purposes": purposes}

def _median_nn(pts):
    if len(pts) < 2:
        return 0.0
    ds = []
    for i, (x, y) in enumerate(pts):
        ds.append(min(abs(x - ox) + abs(y - oy)
                      for j, (ox, oy) in enumerate(pts) if j != i))
    return statistics.median(ds)

def _dedup_identities(objs):
    """Unique identities with a frequency weight (for seeded variety on rebuild)."""
    c = collections.Counter()
    store = {}
    for o in objs:
        ident = OR.exact_identity(o)
        key = (ident["type"], ident["subtype"], ident["animation"], tuple(ident["mask"]))
        c[key] += 1
        store[key] = ident
    return [{"identity": store[k], "weight": w} for k, w in c.most_common()]


def extract_features(name: str) -> dict:
    fm = OR.load_faithful(name)
    W, H = fm["width"], fm["height"]
    levels_out = []
    for L, lvl in enumerate(fm["terrain"]):
        zones, zone_label, canon = _segment_level(lvl)
        zone_objs, _ = _bucket_objects(fm["objects"], L, zone_label, zones, W, H)
        zlist = []
        for zid in sorted(zones):
            z = dict(zones[zid]); z["_zid"] = zid
            prof = zone_features(z, zone_objs[zid], canon[zid])
            prof["label"] = label_zone(zones[zid], zone_objs[zid], W, H)
            zlist.append(prof)
        levels_out.append({"level": L, "zones": zlist})
    return {"name": fm["name"], "width": W, "height": H, "levels": levels_out}

def write_features(name, out=None):
    f = extract_features(name)
    out = out or os.path.join(ROOT, "out", f"zone_features-{slug(name)}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(f, open(out, "w"), indent=1)
    return out, f


# ---------------------------------------------------------------------------
# Deform demo terrain (deterministic, no rng)
# ---------------------------------------------------------------------------

def deform_terrain_level(src_terr, zone, W, H, fx=1.3, fy=1.3):
    """Stretch the zone into a bigger form (nearest-resize of its filled mask, so it
    stays connected and keeps its shape), RESAMPLING the real source terrain cells
    (view/mirror) so the ground matches the original instead of a flat canvas."""
    from PIL import Image
    (minx, miny, maxx, maxy), _ = zone_bbox_mask(zone["tiles"])
    w, h = maxx - minx + 1, maxy - miny + 1
    m = Image.new("L", (w, h), 0)
    mp = m.load()
    for (x, y) in zone["tiles"]:
        mp[x - minx, y - miny] = 255
    nw, nh = max(1, round(w * fx)), max(1, round(h * fy))
    m2 = m.resize((nw, nh), Image.NEAREST).load()
    grid = [[_cell(TS.ROCK, x, y) for x in range(W)] for y in range(H)]  # rock backdrop
    cx, cy = zone["centroid"]
    ox = min(max(int(cx - nw / 2), 0), max(W - nw, 0))
    oy = min(max(int(cy - nh / 2), 0), max(H - nh, 0))
    t = zone["terrain_type"]
    for yy in range(nh):
        for xx in range(nw):
            X, Y = ox + xx, oy + yy
            if not m2[xx, yy] or not (0 <= X < W and 0 <= Y < H):
                continue
            sx = minx + min(int(xx / nw * w), w - 1)   # inverse-map to a source cell
            sy = miny + min(int(yy / nh * h), h - 1)
            sc = src_terr[sy][sx]
            grid[Y][X] = {"t": t, "view": sc.get("view", 0), "rt": sc.get("rt", 0),
                          "rd": sc.get("rd", 0), "ot": 0, "od": 0, "m": sc.get("m", 0)}
    return grid
