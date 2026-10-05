# Effort reward: pay a place by the days it costs

Disclosure. I wrote this note after a whole session inside the existing generator. I had
read its reward, guard, gate, portal and catalog code before the decompose order began, and
the settled grill with the user is in my context. The decisions that reached me that way are
listed as claims in 1b. Each part and concept below was checked against the test "would I
have named this without having seen the solution?" Two names failed it and were renamed:
the generator's "zone" became "place" (the domain word players use is "area", and the grill
already used "place"), and its "loot pocket" became "deep pocket".

## 1. Problem

A player who walks across the map to a Keymaster's tent and back, sails to a far island, or
beats a dragon finds the same handful of gold and a random treasure artifact they would find
next to their castle. The hard places on a generated map do not pay for the days they cost,
so a player has no reason to go there. A player who has installed an expansion or a mod
never sees its artifacts, creatures or objects in a generated map.

Done looks like this, to that player:

- On ten seeds at 72×72, the rewards in cut-off places rise with the days they cost. Each of
  the four effort bands has a higher median reward value than the band below it.
- The hardest places hold the best things the enabled content has: relics, parts of a
  combined artifact, a Pandora's Box with level 6 or 7 creatures or hero levels, a level 6
  or 7 dwelling.
- Every combined artifact whose parts appear on a map appears complete. A 72×72 map with
  one level carries at least one set.
- A map generated with a mod enabled opens in VCMI with that mod active and shows the mod's
  objects. The same map generated with the mod disabled holds none of them.
- The same seed and the same content setting give the same map.

Out of scope:

- Rewards in open places. They keep the plan by distance from home that they have today.
- Mod terrains (Highlands, Wasteland) and mod towns (Cove).
- Quests, seer huts and the Grail.
- Balancing one player's start against another's.
- The army a hero has on a given day. Guard cost is a fixed table by creature level.

## 1b. Claims

Settled with the user in the grill (2026-10-04):

1. Effort is the earliest day a reward can be carried home: guard days plus travel days.
2. A slow starting hero sets the pace. Movement points come from VCMI's game config, terrain
   move costs and road costs.
3. The trip starts at the nearest home. A gate trip runs home, Keymaster tent, gate, reward.
   An island trip runs home, shipyard, sea, landing. Boarding and landing each round up to
   the next day. A monolith or portal counts as one step.
4. Guard cost depends on creature level only: 3, 5, 8, 12, 18, 28 and 45 days for levels 1
   to 7, kept as data.
5. For each guard level L from 0 to 7, take the shortest trip that meets no guard above L.
   Effort is the minimum over L of days(L) plus that trip.
6. The guard comes first and the value follows. Each loot has exactly one guard. A guard
   already on the route is that guard. Otherwise the prize gets its own guard, with its
   level from the corpus reading of guard level by distance.
7. The premium goes only to places cut off by a gate, sea, portal or deep pocket.
8. Four bands, with edges from the corpus effort in front of each artifact class. Each band
   names its kinds. The place's size sets the item count.
9. Set parts go one per place in the top two bands. One set per 72×72 tiles, both levels
   counted, at least one. A set is placed only when enough places exist, and only from sets
   whose parts are all enabled. Parts go round-robin across players by nearest home.
10. The treasure step fills islands too. The rules apply to markov maps too.
11. Effort is measured by one shared function, which each step calls on its own places
    right after placing the opener.
12. The catalog takes the enabled content as a setting: whole mods plus a per-object ban
    list. The default is the base game with AB and SoD. A mod pulls in its dependencies and
    submods. A declared conflict stops generation.
13. Purpose comes from the config handler. A generic rewardable object counts as a
    visitable. Price comes from the artifact value or the object's rmg value. An object with
    no price is never a reward. Mod sprites come from each mod's content archive.

From the existing generator, read before this note:

14. Reward value follows from the guard level through a value ladder (`value.py`).
15. Open places get their content from a plan by hop from home, capped at hop 4.
16. Sealed places get artifacts by fixed class weights: treasure 5, minor 15, major 35,
    relic 45.
17. A portal's far place gets resource piles by its area.
18. A deep pocket's guard level comes from its value.
19. Pandora's Box creatures are a fixed list of nine base-game level 1 creatures.
20. Artifact classes and creature levels are fixed base-game tables.
21. The map writer prefixes every object id with `core:`.

## 2. Parts and concepts

### Level 1: parts

1. **Content.** Owns which expansions and mods are on, and what each enabled object is:
   its purpose, its level or class, its price, its set, and where its picture lives. It
   never knows a map. It answers every other part's questions about objects.
2. **Guarding.** Owns the one guard in front of each prize in a cut-off place: whether a
   guard already on the route serves, or which new guard to stand there and at what level.
   It never knows what the prize is worth. It hands the guards to the map and to Effort.
3. **Effort.** Owns the days a hero needs to reach a prize from the nearest home, guards
   included. It never knows what the prize is. It hands one effort per cut-off place to
   Pricing and to Sets.
4. **Pricing.** Owns the step from effort to a basket: the band, the kinds the band offers,
   how many prizes the place holds, and the concrete enabled object for each. It never
   knows how effort was found. It hands the basket to Placing.
5. **Sets.** Owns the map-wide share-out of combined artifacts: how many sets, which sets,
   and which place gets which part. It never knows the route to a place. It hands one part
   per chosen place to Placing.
6. **Placing.** Owns where each prize stands inside its place: on ground it allows, on a
   free tile, behind its guard. It never knows why the prize was chosen. It writes onto the
   map.
7. **Saving.** Owns the map file and its pictures: each object's scoped id, the list of
   mods the map needs, the sprite drawn for each object. It never knows why an object was
   placed.

The flow. Content resolves the enabled set once, before anything is placed. Then each time
a cut-off place gets its opener (a gate and its tent, a shipyard, a portal pair, or the
walls of a deep pocket), Guarding names the place's guard, Effort measures the place,
Pricing turns the effort into a basket, and Placing stands the basket in the place, holding
one prize back in each top-two-band place. After the last opener exists, Sets shares the
combined artifacts out over the held-back prizes, and Placing stands them. Saving writes
the file and draws it.

In plain words: the game's content decides what may appear. A guard is chosen for each hard
place. We count the days it takes to get there. The days buy a basket of rewards. The
best baskets share out the pieces of a few legendary sets. The rewards are put on the map,
and the map is written so VCMI can open it.

### Level 2: concepts

**Content**

| Concept | Owns | Never knows |
|---|---|---|
| Content setting | the user's choice: mods named on, objects banned | what a mod contains |
| Mod manifest | one mod's declared dependencies, submods and conflicts | the objects in it |
| Enabled set | the closure of the setting over manifests, and the stop on a conflict | object kinds |
| Content archive (role) | reading one file out of a mod's content | which object the file serves |
| Folder archive (variant) | reading from an unpacked mod folder | zip |
| Zip archive (variant) | reading from a mod's packed content archive | folders |
| Object entry | one enabled object's purpose, level or class, price and set | the map |
| Hero pace | movement points per day on land and sea, and the cost of each terrain (revised, R1) | the map |
| Crossing kind | which crossing an object makes and on which channel (new, R2) | routes |

The object entry is the read-only reference every other part consults. An artifact set is a
field of the entry (its parts), not a concept of its own. An object without a price carries
no price, and no part reads one in for it.

**Guarding**

| Concept | Owns | Never knows |
|---|---|---|
| Guard reading | the corpus guard level at each distance from home | effort |
| Prize guard | whether a route guard serves the prize, or the level of a new one | the prize's worth |
| Guard creature | the enabled creature that stands for a level | the place |

**Effort**

| Concept | Owns | Never knows |
|---|---|---|
| Passage rule | what a hero must hold or pay to cross one tile edge: a key, a boat, a one-step teleport, a boarding that ends the day | guard levels |
| Guard toll | the days a guard of each level costs | routes |
| Route search | the earliest day each tile is reached from the nearest home, given a guard ceiling | what is on the tile |
| Effort | the minimum over guard ceilings of toll plus route | rewards |

**Pricing**

| Concept | Owns | Never knows |
|---|---|---|
| Cut-off place | one place and the opener that cuts it off (new, see §5) | its effort |
| Band edges | the four effort thresholds, read from the corpus | the kinds |
| Band basket | the kinds each band offers | effort numbers |
| Prize count | how many prizes a place holds by its size | its band |
| Pandora content | what one Pandora's Box grants for a band | where it stands |
| Prize draw | one enabled, priced object of a kind | bands |

**Sets**

| Concept | Owns | Never knows |
|---|---|---|
| Set quota | how many sets a map of this size carries | which sets |
| Set choice | which complete, enabled sets fit the held-back prizes | geometry |
| Part share | which held-back prize takes which part, round-robin by nearest home | effort |

**Placing**

| Concept | Owns | Never knows |
|---|---|---|
| Prize spot | the free, allowed tile a prize stands on inside its place | why the prize was chosen |
| Held-back prize | the one prize slot a top-two-band place keeps for Sets | which set |

**Saving**

| Concept | Owns | Never knows |
|---|---|---|
| Scoped id | the mod-qualified name of an object in the file | its purpose |
| Mod requirement | the list of mods the file declares, from the objects it holds | why they were placed |
| Sprite source | the bytes of an object's picture, from the base game or a mod archive | the map |

Sprite source reads through the Content archive role. That is a dependency on the role, not
a concept shared by two parts.

## 3. Invariants

1. **The same seed and content setting give the same map.** Owner: the whole map's
   determinism check. Every concept draws from a seeded stream named for its part.
2. **Every placed object belongs to the enabled set.** Owner: Enabled set. It refuses to
   answer for a disabled object, so no draw can return one. Prize draw and Guard creature
   uphold it.
3. **A conflict between enabled mods stops generation with a message.** Owner: Enabled set.
4. **Every prize in a cut-off place has exactly one guard on its route.** Owner: Prize
   guard. Placing upholds it by standing a new guard only where Prize guard asked for one.
5. **Effort is finite for every cut-off place.** Owner: Effort. A place no home reaches is
   a failure, not a zero.
6. **More effort never buys a lower band.** Owner: Band edges. The edges are strictly
   increasing, checked when they load.
7. **An object with no price is never a prize.** Owner: Prize draw.
8. **Every set on a map is complete, one part per place.** Owner: Part share. It places a
   set only when it has a held-back prize for every part.
9. **Every held-back prize is filled.** Owner: Part share. A held-back prize that no set
   takes gets the artifact its place drew from the band's basket, else a resource pile
   (R8).
10. **The saved map declares every mod its objects come from.** Owner: Mod requirement.

## 4. Forces and patterns

### Forces

- F1. The enabled content varies per user and grows as mods appear. No mod name may appear
  in code.
- F2. A mod's content is packed or unpacked depending on how VCMI was installed. The
  flatpak install packs every mod. An older install unpacks them.
- F3. The ways a place is cut off vary: gate and key, sea and shipyard, portal or monolith,
  a deep pocket behind a guard. New ones may come (whirlpools, subterranean gates).
- F4. Band edges and guard tolls are numbers the user tunes, and the corpus supplies.
- F5. Each decision must be testable on a few literal tiles, with no pipeline.
- F6. Places become cut off at different moments, while the set share-out needs every
  top-band place on the map at once.
- F7. Effort runs several times per map, over every tile and up to eight guard ceilings. It
  must stay cheap.
- F8. Both terrain models feed it. Effort reads only the finished ground and objects.

### Between parts

- **A sequence of stages handing frozen values on** (F6). Each stage that cuts places off
  measures and fills them, then publishes the held-back prizes it kept. The set stage runs
  after the last opener and reads every published list. This re-derives claim 11 for
  measurement and splits it for sets: measurement happens right after the opener, and the
  set parts wait for the last one.
- **One read-only content reference** (F1). Every part asks Content. Content is built once
  from the setting, before the first stage.
- **Effort is a plain function, not a stage** (F5, F8). It takes the ground, the passages
  and the guards as plain values, and returns days per tile. Each stage that cuts places
  off calls it.

### Inside a part

- **Content archive is a role with two variants** (F2): folder and zip. The mod loader
  depends on the role, and the setting's install decides the variant.
- **Enabled set is a plain function** over manifests: closure, then the conflict check.
- **Object entry is data read from the mod's own config** (F1): the handler gives the
  purpose, the artifact's value or the object's rmg value gives the price, and an
  artifact's components give its set. A new mod adds no code.
- **Passage rules are data, one rule per kind of crossing** (F3). The route search is one
  shortest-path search over a state of (tile, keys held, on a boat), with days and
  remaining movement as the cost. A gate edge needs its key. A shipyard tile gives a boat. A
  boarding or landing ends the day. A monolith pair is one step. A new kind of crossing adds
  one rule. A trip per opener kind (gate trip, sea trip, portal trip) was rejected: the
  state search finds the tent detour and the shipyard detour on its own, and a fixed trip
  would miss the shorter route through a second opener.
- **Effort runs one search per guard ceiling actually present** (F7). A ceiling with no
  guard at it gives the same route as the ceiling below. The search is multi-source from
  every home at once, so one search serves every place.
- **Band edges, guard tolls, band baskets and the set quota are data tables** (F4).
- **Every other concept is a plain function or a plain value.** No force asks for more.

### Claims re-derived or rejected

- Claims 1 to 10, 12 and 13 are user decisions. The design carries each. Claim 3's
  per-opener trip becomes passage rules (above); the user's trips are what the search
  finds, so the outcome is the same.
- Claim 11 is kept for measurement and split for sets (F6).
- Claim 14 (value from guard) is rejected by claim 6: the guard comes first.
- Claim 15 stays for open places, out of scope.
- Claims 16 and 17 are rejected: band baskets replace fixed class weights and piles by area.
- Claim 18 is rejected by claim 6.
- Claims 19, 20 and 21 are rejected by F1: Pandora creatures, artifact classes, creature
  levels and ids all come from Content.

### Open lookups

- L1. Where the shipyards, Keymaster tents and gates stand, and which step places each.
  Decides where the passage rules read their tiles.
- L2. The pipeline order today. Decides which stage runs the set share-out.
- L3. Whether the catalog port can take a setting at construction, and every caller that
  builds it. Decides the Content wiring.
- L4. How sprites are found today. Decides whether Sprite source is new or a reshape.
- L5. Whether the corpus reading already measures guard level by distance and artifact
  positions. Decides how Band edges and Guard reading are fed.
- L6. Whether the vmap header can carry a mods list. Decides Mod requirement.
- L7. The time one route search takes on a 72×72 map with two levels. Decides whether F7
  needs compiled code.

### SOLID check

- Single responsibility: each Owns above reads without "and". Hero pace owns "movement
  points and costs" as one table of numbers read from one config.
- Open/closed: a new archive format adds one variant and one line in the setting. A new
  crossing adds one passage rule. A new mod adds data only.
- Liskov: folder and zip archives are each a kind of Content archive, never of each other.
- Interface segregation: Content archive declares one call, read a named file.
- Dependency inversion: the mod loader's never-knows names zip and folder.

## 5. Mapping onto the existing system

### Revision log

- R1. §2 Effort, Hero pace moves to Content. VCMI's movement numbers reach the core only
  through the catalog port (`core/catalog.py`), and the catalog already keeps static tables
  taken by hand from VCMI config (`vcmi/catalog/tables.py` L84-100). Hero pace is now a
  field of Content that Effort reads.
- R2. §2 Effort, Passage rule reads each crossing's kind from Content. The core may not
  name a VCMI type (`Trait` docstring, `core/catalog.py` L22). Content answers "what
  crossing is this object, and on which channel" (key colour, monolith pair, level gate).
- R3. §4 Inside a part, the key state shrinks to one key. A cut-off place behind a gate
  holds no town and no purposeful object (`gated/placer.py` `_eligible` L341-349), so no
  key ever sits behind another gate. The search for a gated place carries one bit, "holds
  this place's key", and runs once per key colour present. The general key set is dropped
  until a nested gate exists.
- R4. §2 Guarding, Guard reading is flat past hop 2. The corpus mean guard level is 2.51
  at hop 0, 2.82 at hop 1 and about 2.95 from hop 2 on, and level 7 is rare (24 guards at
  hop 0). Prize guard draws the level from the corpus spread at the place's hop, not from
  the mean, so a strong guard still appears and lifts the band.
- R5. §2 Pricing, Band edges are mined from artifact positions the corpus reading does not
  keep today. A new corpus miner measures effort at every artifact pickup of each class.
- R6. §1b claim 3, roads. Roads are laid last (`cli/steps.py` L76-95), after every reward.
  Effort ignores roads on both sides, generated and corpus, so the band edges and the
  measured places agree (A4).
- R7. §2 Pricing gains Cut-off place, from the finding under "What the existing system has".
- R8. §3 invariant 9 falls back to the place's own basket artifact, not the band's top
  one. The basket already prices the place, and a top artifact on every unused slot would
  flood band 3 and 4 places with relics. A slot whose artifact no longer fits takes a
  resource pile of its terrain.
- R9. §2 Sets, a seer-hut quest never asks for a set part or a combined artifact. A quest
  for a part the set dealer also placed would hand the hero a second copy, and a quest for
  a part it did not place would leave a partial set on the map (invariant 8).
- R10. §3 invariant 8 holds for the parts the generator places. The band baskets place
  VCMI's random artifact of a class, and VCMI rolls it at game start. That roll may give a
  set part, so a played map can show a stray part. Closing this needs the baskets to name
  each artifact, which waits on S6.
- R11. §2 Content, Object entry refines a rewardable object's purpose by its reward keys.
  A generic `configurable` handler covers mana wells, stat shrines and banks alike, so the
  handler alone cannot give the purpose. `data/catalog/mod_purposes.json` maps each
  handler, and each reward key in order, to a purpose.
- R12. §2 Content, a mod object joins only the purposes the generator already places as
  visitables: banks, permanent stats, spells and skills, temporary bonuses, mana and
  information. Markets, mines and dwellings from a mod stay off the map until a step asks
  for them, so a mod never replaces a town's economy.
- R13. §2 Content, a mod names a terrain by its config id, such as `subterra`. Each
  terrain carries that id beside its name, so the catalog's terrain names stay the only
  ones the core sees.
- R14. §2 Saving, Scoped id is dropped. VCMI resolves a mod object by its bare type and
  subtype once the header lists the mod, so the export writes bare names for every object.
- R15. §2 Content, a template whose animation the base game holds stays the base game's.
  HotA's submods re-declare base trees and bushes, and counting those as mod objects
  would make every vegetated map require HotA.
- R16. §2 Saving, Sprite source is a Content archive itself: the base game first, then
  each enabled mod's `sprites` folder. The renderers read any Content archive, so they
  never learn that mods exist.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Content | Reshape | `core/catalog.py` port and `vcmi/catalog/`. It answers object questions but takes no setting, reads only the four LOD files (`vcmi/formats/lod.py` L8), and `load_config` reads every mod folder unfiltered (`vcmi/config.py` L132-142). |
| Guarding | Reshape | Spread over `gated/placer.py` `_guard_partner` L663-673 (always `guard(7)`), `portal/rescue.py` L428 (`4 + area//60`), `portal/reward_zone.py` L77 and `loot/pickups.py` L355, L510 (value ladders). Four rules, none from distance. |
| Effort | New | `core/reading/effort.py`. Both the corpus miner and the steps call it, as they share `core/reading/`. |
| Pricing | Reshape | `treasure/fill.py` `_LOOT_ART_W` and `_roll_spec`, `portal/reward_zone.py` pile count, `loot/pocket_plan.py` `ART_TIER_BY_GUARD_LEVEL`. Three fixed rules become one band basket. |
| Sets | New | `core/steps/sets/`, a step after `loot`. |
| Placing | Exists | `CoverIndex.try_claim`, `core/placement/ground.stands`, and each step's fill loop. Held-back prize is new. |
| Saving | Reshape | `vcmi/export.py`, `vcmi/options.py` (`core:` prefix at L157-198), `vcmi/formats/vmap/writer.py`, `renderers/sprites.py`. |

### Concepts

- Content setting, Mod manifest, Enabled set: New, `vcmi/content/`. The CLI builds the
  setting and hands it to `VcmiCatalog`.
- Content archive with folder and zip variants: New, `vcmi/content/archive.py`. Today
  `zipfile` serves only `.vmap` files.
- Object entry: Reshape. `vcmi/catalog/objects.py` derives identity from the editor table
  and the static tier tables (`tables.py` L102-112). Mod objects need entries from their own
  config.
- Hero pace: New, `data/catalog/pace.json`, read through a Catalog method (R1).
- Passage rule: New, `core/reading/effort.py`, with the crossing kind from a Catalog
  method (R2).
- Guard toll: New, a data table in `data/pp/effort.json`.
- Route search, Effort: New, `core/reading/effort.py`.
- Guard reading: Reshape. `data/pp/place_stats*.json` content rows already hold each
  place's guard levels by hop (`corpus/places.py` L66-67). Prize guard reads them.
- Prize guard: New. It replaces the four rules listed under Guarding.
- Guard creature: Exists, `Catalog.guard(level)`.
- Band edges: New, mined into `data/pp/effort.json` by `corpus/mine/effort.py` (R5).
- Band basket, Prize count, Prize draw: Reshape of `treasure/fill.py`.
- Pandora content: Reshape of `core/placement/rewards.py`, whose creatures are nine fixed
  level 1 names (L9-19).
- Set quota, Set choice, Part share: New, `core/steps/sets/`.
- Prize spot: Exists. Held-back prize: New, a field of each filling step's result.
- Scoped id, Mod requirement, Sprite source: Reshape of the files under Saving.

### What the existing system has that the design lacks

- `ContentPlan` by hop for open places. Out of scope. It stays.
- Seer hut quests. Out of scope. They stay.
- Island detection (`core/placement/water.py` `_is_island` L531-539) is private, and no
  result says whether a place is an island, behind a gate or behind a portal. The design
  missed a concept: **Cut-off place**, the place and the opener that cuts it off. It is a
  shared value type the opening steps publish and Pricing reads. Added to Pricing's inputs.
- The level-7 guard on every Keymaster tent and outer monolith. Waste under claim 6: it
  pushes every gated place into band 4.

### Claims against the existing system

- Claims 1 to 13: the existing system follows none. The design carries each.
- Claim 14: the existing system follows it in pockets and portal places. The design drops it.
- Claim 15: followed by both.
- Claims 16 to 21: followed by the existing system, dropped by the design.

### Lookups

- L1. Shipyards stand in gameplay (`gameplay/step.py` L329-334, surface only). Tents and
  border gates stand in gated (`gated/placer.py` L497-513). Portals stand in portal. The
  passage rules read all of them from the finished objects, so the step order does not
  matter to Effort.
- L2. `terrain, vegetation, gameplay, gated, treasure, portal, loot, scatter, roads`. Sets
  runs after loot.
- L3. `VcmiCatalog` is built in `cli/` and in tests. It takes no setting today. Content
  wiring adds one constructor argument with the base-game default, so no caller breaks.
- L4. Sprites come from `LodIndex` only. Sprite source is a reshape.
- L5. Guard by hop exists, artifact positions do not (R4, R5).
- L6. The vmap header has no mods key, but `VmapDocument.extra` round-trips any key, so
  Mod requirement writes one there.
- L7. Unmeasured. It becomes A3.

## 6. Slices

1. **S1. Gated places pay by their days.** Touches Content (Hero pace, crossing kinds),
   Effort (all), Pricing (Band edges, Band basket for artifact class only), and the
   corpus miner. The treasure step measures each gated place and draws its artifact class
   from the band. Done when: `make check` is green; an effort report on ten seeds prints
   each gated place's days and band; and the median reward value rises band by band.
2. **S2. The guard comes first.** Touches Guarding (all). The tent and monolith partner
   guards, the portal guard and the deep pocket guard take their level from the corpus
   spread at the place's hop. Done when no cut-off place's guard level is computed from
   its value, and the report shows bands 1 to 4 all present over ten seeds. Result: the
   four guards draw from `core/planning/guarding.py`. Ten 72×72 seeds hold only five
   gated places, too few to cover four bands, so the report reads 30 seeds: 11 places
   with bands 1 to 4 holding 3, 1, 4 and 3.
3. **S3. Islands and portal places pay too.** Touches Cut-off place, Pricing, Placing.
   Islands and portal places get band baskets. Done when the report lists islands and
   portal places with their bands, on markov and places maps.
4. **S4. Sets.** Touches Sets (all), Held-back prize. Done when every 72×72 seed carries
   at least one complete set and no partial set appears. Result: ten places seeds, five
   two-level seeds and five markov seeds at 72×72 each carry their full quota, one set per
   level, every part on a band 3 or 4 slot, and no held slot stays empty.
5. **S5. Pandora and dwellings by band.** Touches Pandora content, Band basket. Done when
   band 4 places hold level 6 or 7 Pandora creatures or dwellings on some seeds.
   Result: each band carries one offer in `effort.json`: its artifact basket, its
   Pandora grant and its box count. Bands 3 and 4 place one Pandora's Box per place, and
   a box draws its creatures by level from the catalog, levels 6 and 7 in band 4. Six
   72×72 seeds hold four band 4 places, and one of them grants a level 6 stack. The
   dwellings by band are left for later, because the Pandora grant alone meets the bar.
6. **S6. Content setting.** Touches Content (all). Done when the default setting keeps
   the golden hashes of S5, and a setting that bans an object keeps it off every map.
   Result: `vcmi/content/` reads every installed `mod.json` and resolves a setting of
   named mods and banned names into the enabled set. A named mod pulls in its dependencies,
   a submod joins when its own dependencies are enabled, and a declared conflict or a
   missing mod stops generation. `VcmiCatalog` drops every banned object, artifact, spell
   and creature from its pools, and a set with a banned part. `generate` and
   `render-vegetation` take `--mods` and `--ban`. The default setting keeps the four golden
   hashes, and a seed-1 map with six of its own objects banned holds none of them.
7. **S7. Mods.** Touches Content archive, Object entry, Saving. Done when a map generated
   with one mod enabled opens in VCMI with that mod required and shows its objects.
   Result: `generate --mods hota` reads 37 placeable HotA objects, each with its own
   sprite. A seed-3 map at 72×72 places HotA's Colosseum of the Magi with its own mask,
   its header requires `hota` and `hota.mapobjects`, and the render draws the mod's
   sprite. The same seed without the mod holds no HotA object, and the four golden hashes
   hold. A mod object draws at the lowest corpus weight because no corpus map holds it,
   so a map holds zero or one of them. Mod artifacts and creatures are not read yet.

## 7. Assumptions

1. **Assumption:** the corpus effort at artifact pickups orders the four classes, so the
   class medians increase. **Decided:** band edges sit at the geometric midpoints between
   consecutive class medians. **Basis:** S1 measured the class medians over the corpus:
   treasure 6, minor 11, major 16 and relic 31 days. They rise, so the edges are 8, 13
   and 22 days. **If wrong:** §2 Band
   edges, §3 invariant 6. A fallback is an even split of the corpus effort range by
   quantiles.
2. **Assumption:** a gated place's prize stands a few tiles past its opener, so the effort
   at the opener is the place's effort. **Decided:** Effort is read at the cheapest of the
   opener's interactive tiles, the gate or the monolith a hero steps on.
   `LootAccess.entry` is not the measure point, because vegetation may stand on it
   (seed 2 at 72×72). **Basis:** S1's run over seeds 1 to 8. **If wrong:** S1's measure
   point.
3. **Assumption:** one route search over two 72×72 levels runs in well under a second in
   plain Python. **Decided:** no compiled code in S1. **Basis:** none. S1 times it. **If
   wrong:** §4 F7, compile the search with numba as the vegetation sampler does.
4. **Assumption:** ignoring roads changes no band. **Decided:** Effort reads no roads.
   **Basis:** roads cut a tile's cost by 25 to 50 percent, but on a few tiles of each
   route, and the band edges ignore them too. **If wrong:** R6, and roads must run before
   the reward steps.
5. **Assumption:** a monster guards its own tile and its eight neighbours, and a hero who
   enters any of them fights it. **Decided:** a tile's guard level is the highest level
   among monsters within one tile. **Basis:** Heroes III's zone of control. **If wrong:**
   §2 Passage rule.
6. **Assumption:** a diagonal step costs √2 times the terrain cost, and a hero's day ends
   when its movement points run out, with the remainder kept as a fraction of a day.
   **Decided:** the search adds day fractions and rounds up at boarding, landing and at the
   end. **Basis:** VCMI's movement rules; slow hero 1500 points (`gameConfig.json` L528).
   **If wrong:** §2 Hero pace.
7. **Assumption:** the static pace table matches every user's install. **Decided:** pace
   is a table taken from VCMI config, like the creature levels, so the same seed gives the
   same map on every machine. **Basis:** `vcmi/catalog/tables.py` L84-100. **If wrong:**
   regenerate the table, nothing else.
