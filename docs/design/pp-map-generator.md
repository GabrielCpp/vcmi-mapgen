# The PP map generator: a top-down decomposition

Status: draft for review, 2026-09-28. Nothing here is approved.

Problem statement: `docs/specs/pp-map-generator-solution.md`. Where that spec and the design
settled on 2026-09-27 disagree, the settled design wins. That design places every gameplay
object after vegetation (`docs/plans/gameplay-after-vegetation.md`).

Reading order, stated honestly. Sections 1 to 4 were written before any source file was
opened. The domain documents read first still name modules on almost every page:
`docs/architecture/target.md`, the plan above and the `AGENTS.md` files. Each concept in
section 2 was checked against the question "would I have named this without those
documents?" Three concepts fail that check in part, and section 2 marks them.

## 1. Problem

A Heroes III player who wants a fresh map for a group today has two choices. They draw one
by hand for hours, or they take a template map that looks nothing like the hand-made maps
they know.

Done means this for that player. They run one command with a seed, a size, a player count
and a team split. They get a map file that opens in the VCMI editor with no warnings and
plays at once. Each player owns a town near the middle of a large zone, with a sawmill and
an ore pit close by. Every town, mine and treasure can be reached on foot or by boat. Every
guard's strength matches what it guards. The forests hug the buildings the way they do on
real maps. The same seed gives the same file, byte for byte. A likeness report puts each
object type inside the corpus band on edge depth, passage distance, openness and back
contact.

Out of scope:

- Turning the `.h3m` corpus into `.vmap` files. That extraction exists and this note uses
  its output.
- The underground level and its subterranean gates. The spec covers one surface level.
- Sealed loot zones, portal pairs, seer-hut quests and border closing. The spec names
  relational chains as future work.
- Roads, rivers and placed heroes.
- Start fairness beyond dispersion, such as mirroring mine sets between players.
- The target architecture's core and adapter split, and the 45-second corpus rebuild on
  every run. `target-architecture` owns both.
- Installing maps into the VCMI Maps folder. Outputs stay in `out/`.

## 2. Concepts

| Concept | Owns | Never knows |
|---|---|---|
| Random stream | Deriving an independent seeded stream for one layer and one region | What the draws are for |
| Corpus survey | Measuring statistics from the corpus maps | How the generator uses them |
| Priors | The measured statistics as read-only values | Object identity, which the Catalog owns |
| Catalog | What an object is: identity, footprint, terrain coupling, purpose, decoration category, random-class variants | How often or where objects appear |
| Terrain layout | The terrain of every tile: water mask, zones grown to corpus sizes, textured borders | Objects of any kind |
| Tile art | Which picture each tile shows | Zones and objects |
| Zone | A same-terrain connected land region | Water and rock, which are never zones |
| Water body | A connected water region | Land zones |
| Passage | The open band of a border between two zones and its narrowest tile | Vegetation |
| Walkable web | The tiles that must stay walkable so every passage and every approach connects | How vegetation or gameplay is chosen |
| Player zones | Which zones start a player, dispersed by distance | Slots, teams and ownership |
| Vegetation | Decoration whose texture matches the corpus statistics for its terrain | Gameplay purposes and identities |
| Zone budget | How many gameplay objects a zone gets, split by the corpus mix | Where they stand |
| Economy ledger | Which mine resource comes next, map-wide | Mine positions |
| Object choice | The concrete or random-class identity drawn for a purpose | Positions |
| Placement rule | Whether one object may stand on one spot | Which spot is best |
| Site preference | Ranking the legal spots for one object | Whether a spot is legal |
| Guard | The fight between a hero and a prize: its post at the prize's chokepoint, its level from the prize's value | Creature data, which the Catalog owns |
| Pocket | A dead-end nook of the finished open ground and its mouth | What goes inside |
| Cache | A guarded reward inside a pocket, valued for its guard | Pocket geometry |
| Scatter | Unguarded removable objects on open ground, spaced apart | Pockets |
| Water population | Objects that float on a water body | Land objects |
| Landing | The one shore spot per large water body kept open for a shipyard before vegetation grows | Which shipyard identity stands there |
| Reachability audit | The verdict whether every target is reachable, islands allowed | How to repair a failure |
| Scenario | Player slots, teams, town ownership and the victory rule | Zone geometry |
| Map | The committed tiles and objects, appended to and never edited | How objects were chosen |
| Map file | The map in the editor's format | Generation |
| Preview | The map drawn with real sprites | Generation |
| Likeness report | Each object type measured on generated and corpus maps, with a verdict | How the generator placed them |

Three rows fail the "without the documents" check in part. The Walkable web's approach links
come from the settled plan, not the spec. The spec builds the web from approaches before
gameplay exists. Scenario absorbs what the spec calls a post-export patch. The Likeness
report comes from the settled plan's proof story.

Landing was added after section 5 read the code. The spec treats the shipyard as one more
gameplay object. The code showed that a shipyard's shore spot must be kept before any tree
grows, or vegetation walls every shore. Nothing in the first draft owned that spot.

Guard is one responsibility with two faces. Both its post and its level derive from the
prize, so they cannot vary apart.

### Flow

1. The Corpus survey measures the corpus once, offline, and writes the Priors. The Catalog
   is static.
2. From the seed, the Random stream hands each layer its own stream.
3. The Terrain layout draws the water mask, grows the zones and textures their borders.
4. Segmentation of that terrain yields Zones and Water bodies.
5. Passages open on every zone border. Water population fills each Water body, and each
   large Water body gets its Landing. Player zones are picked, and each keeps room for its
   town.
6. The Walkable web connects every passage, Landing and kept town room in each zone.
7. Vegetation fills each zone. The web and the reserved room are hard zeros.
8. Per zone, the Zone budget sets the total and the mix. The Economy ledger picks each mine
   resource. Object choice picks the identity. Site preference ranks spots, the Placement
   rule accepts one, and the Map commits it. The Guard follows its prize. Each object's
   approach links to the web.
9. On the finished open ground, Pockets are found, Caches fill them, and Scatter spreads
   the rest.
10. The Reachability audit judges the map.
11. The Scenario sets players, teams, owners and victory.
12. The Map file and the Preview are written. Tile art is computed for them only.
13. Offline, the Likeness report compares generated maps with the corpus.

Section 5 moved Water population from after gameplay to step 5. The Landing plan needs the
sea objects first, and vegetation needs the Landing.

## 3. Invariants

| Invariant | Enforced by |
|---|---|
| The same seed, size and options give a byte-identical map file. | Random stream: every draw comes from a derived stream, and each region's stream ignores other regions' draw order. |
| Identity, footprint, terrain coupling and category come only from the catalog. The corpus never decides them. | Catalog |
| Generation never measures the corpus. A missing or stale statistic is an error that names the survey command. | Priors |
| Zone sizes follow the corpus area distribution, and two adjacent zones never share a terrain. | Terrain layout |
| Water and rock are never zones. | Zone |
| Every passage keeps at least `max(3, round(open fraction × front length))` tiles open. | Passage |
| No vegetation lands on the walkable web or on a kept town room. | Vegetation |
| The walkable web never splits. A gameplay object may cut a web tile only when the web reroutes around it. | Walkable web |
| Every gameplay approach connects to every passage of its zone on foot. | Walkable web |
| A committed object is never moved or removed. No object covers another object's visit tile or approach. | Map |
| Gameplay bodies never overlap each other. Gameplay blocking cells keep a 2-tile gap. Bodies may stack on vegetation. | Placement rule |
| A zone's total holds its forced objects. When they exceed it, the zone gets nothing else. | Zone budget |
| Every map holds all six basic mine resources. Gold mines stay below the town count. Every town's zone holds a sawmill and an ore pit. | Economy ledger |
| Every mine has a guard on its approach. Every guard is a random-level monster. No two guards stand within Chebyshev 2. A guard's level never falls as its prize's value rises. | Guard |
| Every coastal water body large enough gets one shipyard. | Landing |
| Player zones are chosen by greedy max-min centroid distance. | Player zones |
| Exactly N slots are playable, and each owns its town on the town object itself. | Scenario |
| Every visitable object carries its approach directions in the file. | Map file |
| No map file is written for a map that fails the audit. | Reachability audit |

## 4. Forces and patterns

### Forces

- F1. The corpus pass is slow and its output changes only when the corpus or the survey
  changes. Generation must stay fast.
- F2. Tests need a small catalog and small statistics without patching globals. A map-wide
  ban would also shrink the catalog.
- F3. The layers run in a fixed order, and each writes the shared map. A run can stop after
  any layer to inspect it.
- F4. Many rules each accept or reject a spot, and the rule set differs by layer.
  Vegetation may stack. Guards may stand on the web. Gameplay may not touch gameplay.
- F5. A spot's rank combines independent terms: corpus intensity, back contact, and the
  player town's pull to the centre. The settled design added one term, and the next tuning
  will add another. The terms are not in one unit: intensity is a weighted random order,
  back contact is a count of walled cells.
- F6. Guard rules vary by prize kind: mine, passage, cache, roaming and sea.
- F7. Mine coverage is a map-wide constraint, and zones are placed one at a time.
- F8. The water mode varies at run time: none, normal or islands.
- F9. The likeness proof compares an output with a reference under a tolerance that is not
  known yet.
- F10. Tile art is needed by the file and the preview, and never by generation.

### Patterns

| Concept | Pattern | Force |
|---|---|---|
| Priors | Cache stored as data, versioned, loaded once per run | F1 |
| Corpus survey | A separate command, the only writer of the priors | F1 |
| Catalog | Port with one production adapter, handed to the pipeline | F2 |
| Layers, as steps | Pipeline of steps with typed inputs and outputs | F3 |
| Placement rule | Chain of predicates, one chain per layer | F4 |
| Site preference | Term functions compared in a fixed order, as a sort key | F5. Section 5 changed this from a weighted sum, because the terms share no unit. |
| Guard | A dict of level rules keyed by prize kind | F6 is weak. The variants are tables, not behaviour. |
| Economy ledger | A plain value passed through the zones in sorted order | F7. No pattern beyond a value. |
| Terrain layout | A function with a water-mode parameter | F8 is weak. The modes differ in two numbers. |
| Likeness report | Oracle: measure, reference, tolerance and verdict as separate parts | F9 |
| Tile art | A plain function both outputs call | F10 is weak. |
| Random stream | A plain function of seed, salt and region id | No variation |
| Every other concept | A plain function or a plain value type | No force today |

The spec keeps players as a patch applied after the file is written, to protect a writer
another pipeline shared. That pipeline is gone, so no force keeps the patch. The Scenario is
data the Map file writes.

### Open lookups

- L1. Does generation still measure the corpus on each run? Decides whether F1's cache
  exists or is new.
- L2. Do placement layers reach the catalog through one handed-in object or through module
  globals? Decides whether the Catalog is Exists or Reshape.
- L3. Is legality one check per layer, or copied inside each placer? Decides F4's chain.
- L4. Does site ranking already sum intensity and back contact as separate terms?
- L5. Is there one zone total with forced objects inside it?
- L6. Is the mine ledger map-wide, and does it hold gold below the town count?
- L7. Are guards spaced at placement, or deduplicated after?
- L8. Does a reachability audit exist, and does anything repair by deleting objects? This
  decides whether the audit invariant holds against the additive-map invariant.
- L9. Are player zones chosen before vegetation, with room kept for the town?
- L10. Does the Scenario live in the writer, or in a patch after it?
- L11. Is there a likeness report, and is it a test yet?
- L12. Is each region's stream derived from its id, or drawn in sequence from one stream?

## 5. Mapping onto the code

### Verdicts

| Concept | Verdict | Where | Finding |
|---|---|---|---|
| Random stream | Reshape | About 20 call sites, from `steps/terrain_gen/` to `steps/scatter/` | Each site mixes the seed with a region id, a multiplier and a salt by hand. No shared function exists. See M10. |
| Corpus survey | Reshape | Survey functions in `steps/terrain_gen/macro_topo.py`, `steps/vegetation/stats.py`, `steps/gameplay/mines.py` and `steps/gate/gates.py` | The survey code sits beside each consumer and runs on a cache miss in the middle of a generation run. No single command writes the priors. |
| Priors | Reshape | `data/pp/*.json`, committed | Four of six statistics are cached. The Markov border model and the tile art table learn from all 159 maps on every run. Only the gameplay and gate files carry a version. See M11. |
| Catalog | Reshape | `ontology.py` | The pipeline receives an `Ontology` instance, but 19 modules call the module-level accessors. A test cannot hand in a small catalog. See M12. |
| Terrain layout | Exists | `steps/terrain_gen/` | Owns and never-knows match. It also computes tile art. See M13. |
| Tile art | Reshape | `kit/tiling.py`, called from the terrain step | Generation computes it, and it reads the corpus each process. See M13. |
| Zone | Exists | `kit/terrain_segment.py`, `steps/segment/` | Water and rock are barriers. The zone plan drops zones under 25 tiles. |
| Water body | Exists | `steps/zone_plan.py` | A flood fill over water tiles. |
| Passage | Reshape | `kit/topology.py`, planned in `steps/zone_plan.py` | The code opens one or two fixed 3-tile entrances per zone pair and densifies the rest of the border. The spec opens a band sized by the corpus open fraction. See M1. |
| Walkable web | Exists | `steps/vegetation/sample.py`, extended in `steps/gameplay/site.py` | Built from entrances, landings and town rooms before vegetation. Each committed approach links to it. A cut web reroutes. See M2. |
| Player zones | Exists | `steps/gameplay/mines.py`, room kept in `steps/zone_plan.py` | Greedy max-min on centroid distance, largest zone first, only zones with room for a town. Chosen before vegetation. |
| Vegetation | Exists | `steps/vegetation/` | Hard zeros on the web and the town room hold. The vegetation layer also builds the whole zone plan. See M14. |
| Zone budget | Exists | `steps/gameplay/draw.py` | One total per zone at the corpus rate. Forced objects count inside it. A moved town or a shipyard spends slots after the draw. |
| Economy ledger | Reshape | `steps/gameplay/mines.py`, consumed in `draw.py` and `step.py` | Map-wide and passed through zones in sorted order. A basic mine that finds no spot only prints a warning. See M7. |
| Object choice | Exists | `steps/gameplay/draw.py`, `ontology.pick` | It shares one class with the Zone budget. See M15. |
| Placement rule | Reshape | `validate.py`, `models/map_state.py`, `steps/gameplay/site.py`, `steps/placement.py`, `steps/gated/placer.py` | The terrain rule and the cover rule are shared and the map re-checks them on commit. The zone-local rules (gap, reach, doors, mine front) are copied per placer. |
| Site preference | Exists | `steps/gameplay/site.py` | Centres come in intensity order or centroid order. Inside each 5x5 window, spots sort by back contact, then distance. It is a sort key, not a sum. See M4. |
| Guard | Reshape | `steps/gameplay/site.py`, `gate_pairs.py`, `steps/loot/caches.py`, `steps/border/`, `steps/placement.py` | Level rules live in three places. Spacing is checked by the border and cache guards only. See M5. |
| Pocket | Exists | `steps/loot/caches.py` | Not inspected beyond its guard spacing call. |
| Cache | Exists | `steps/loot/caches.py` | Not inspected beyond its guard spacing call. |
| Scatter | Exists | `steps/scatter/` | Runs last. Keeps off every guard's zone of control. |
| Water population | Exists | `steps/zone_plan.py`, `steps/gameplay/water.py` | Drawn before vegetation, committed first by the gameplay layer. See M3. |
| Landing | Exists | `steps/zone_plan.py` | One landing per shore, joined to the web, kept free of vegetation. |
| Reachability audit | New | Reshape `kit/reachability.py` into a check the CLI runs before writing | That module is imported by one test only, and its docstring names deleted modules. Vegetation raises on a walled-off pocket, and a portal pair rescues an unreachable zone. No check runs on the finished map. See M8. |
| Scenario | Reshape | `renderers/vmap.py` | The writer applies slots, teams, owners and victory after building the document. It sizes the slots from the towns placed, not from the players asked for. See M6. |
| Map | Exists | `models/map_state.py` | Appends and checks only the new objects. `set_objs` replaces the list and has no caller. |
| Map file | Exists | `renderers/vmap.py`, `vcmi/formats/vmap/` | Sets visitable directions on every object. |
| Preview | Exists | `renderers/png.py` | |
| Likeness report | Reshape | `corpus/match.py`, `cli corpus-match` | Measures the four measures and the per-zone counts, and prints means and percentiles. No tolerance, no verdict, not in `make check`. It builds its maps from `cli/steps.py` `build_steps`. See M9. |

### Open lookups resolved

- L1. Yes, in part. Border texture and tile art read the whole corpus on every run. The
  other four statistics come from committed files and are re-measured only when a file is
  missing.
- L2. Both. The instance is handed in, and most modules use the module globals.
- L3. Split. Terrain and cover rules are shared. Zone-local rules are copied per placer.
- L4. No. The terms form a sort key. Section 4 now says so.
- L5. Yes.
- L6. Map-wide, yes. The gold cap counts player towns only. Neutral towns do not raise it.
- L7. At placement, but only for border and cache guards. Mine guards and gate-pair guards
  skip the spacing check.
- L8. No audit runs. Nothing repairs by deleting. The only repair adds a portal pair.
- L9. Yes.
- L10. In the writer, as a step after the document is built.
- L11. A report exists. It is not a test.
- L12. Derived from the region id, with a hand-mixed expression at each site.

### Mismatches

- M1. Passage width. The spec opens a band of `max(3, round(open fraction × front))`
  tiles. The code opens one or two 3-tile entrances per zone pair and closes the rest. The
  code keeps chokepoints for the border guards. The spec keeps borders as open as real maps.
  Neither side is clearly wrong. Decision Q1.
- M2. Web invariant. Section 3 first said no blocking cell lands on the web. The code lets
  gameplay cut a web tile when the web reroutes. The concept was wrong: the web exists for
  connectivity, and a rerouted web keeps it. Section 3 now holds two invariants, one for
  vegetation and one for connectivity.
- M3. Water population order. The first flow placed it after gameplay. The code draws the
  sea objects before vegetation because the landing plan needs them. The concept was wrong.
  Section 2 now has a Landing concept and the new order.
- M4. Site preference pattern. Section 4 first chose a weighted sum. The code uses a sort
  key, and its terms share no unit. The pattern was wrong. Section 4 now says sort key.
- M5. Guard spacing. The border and cache guards refuse a spot within Chebyshev 2 of
  another guard. Mine guards and gate-pair guards check only terrain and cover. The code is
  wrong, because the invariant has one enforcer on paper and three partial ones in the code.
- M6. Player slots. The writer counts the towns that landed, so a 4-player request that
  placed 3 towns writes a 3-player file after a warning. A team split that does not match
  raises in the writer, after the whole run. The code is wrong.
- M7. Six basics. A basic mine with no spot goes back to the ledger. If no later zone
  takes it, the run prints a warning and writes the file. The code is wrong: the invariant
  is a wish there.
- M8. Audit. No check runs on the finished map. Two partial checks exist in other layers.
  The code is missing a concept.
- M9. Likeness. The report has measures and a reference but no tolerance and no verdict.
  The code is missing half of the oracle.
- M10. Stream independence. The sealed-zone placer and the treasure fill build the same
  stream expression for the same zone, so their draws are correlated. The byte-identical
  invariant still holds. The independence claim does not. The code is wrong.
- M11. Priors. Two statistics are relearned every run, and the survey is spread over four
  consumer modules. The code is wrong. Parked, P1.
- M12. Catalog. Module globals defeat the handed-in instance. The code is wrong. Parked, P2.
- M13. Tile art. Generation computes it. The code is wrong. Parked, P3.
- M14. Layers. The vegetation layer builds the zone plan, and later layers mutate one
  shared workspace. The code is wrong. Parked, P4.
- M15. Zone budget and Object choice share one class. The code blurs two concepts at low
  cost. No action.

## 6. Slices

The pipeline already runs end to end, so every slice widens a path that works.

1. **Walking skeleton: no broken file.** Concepts: Reachability audit, Map file. The CLI
   runs the audit on the finished map before writing. A pass writes the file and prints one
   line. A fail writes nothing, exits non-zero and names the first unreachable object. Done
   when `generate --seed 3 --size 72 --players 4` prints the audit line, and a test map with
   a walled-in town writes no file.
2. **One object type has a verdict.** Concepts: Likeness report. The report gains a
   tolerance and a pass or fail per measure for mines only. Done when the report prints a
   verdict per measure for mines on seeds 1 2 3.
3. **Every seat is real.** Concepts: Scenario, Player zones. A request for more players
   than zones can host fails before the costly layers. The Scenario takes the requested
   count and the team split as values, and a mismatch fails at argument parsing. Done when
   every written file read back holds exactly N owned towns.
4. **Every map has the economy and fair guards.** Concepts: Economy ledger, Guard,
   Placement rule. A missing basic mine fails the run. Every guard goes through one spacing
   check. The audit grows both checks. Done when a 20-seed sweep writes no map missing a
   basic and no two guards within Chebyshev 2.
5. **Borders pass the likeness test.** Concepts: Passage, Walkable web, Likeness report.
   Apply Q1, and add border openness to the report. Done when border openness passes the
   verdict on seeds 1 2 3.
6. **Every type has a verdict.** Concepts: Likeness report. Widen slice 2 to every counted
   type and add it to `make sweep`. Done when the sweep fails on a type outside its band.

## 7. Open decisions

**Q1. Passage width.** Keep the code's one or two narrow entrances per zone pair, or open
the spec's corpus-sized band?

Recommendation: keep the narrow entrances and rewrite the passage invariant to "every
adjacent zone pair shares one or two entrances at least 3 tiles wide". The border guards
need a chokepoint, and slice 5 tests the choice against the corpus.

**Q2. Audit failure.** When the audit fails, refuse to write, or retry with the next
derived seed?

Recommendation: refuse and name the unreachable object. A retry breaks "same seed, same
file" and hides the bug that caused the failure.

**Q3. Repair.** The spec repairs an unreachable target by carving vegetation, which
deletes objects. The code rescues an unreachable zone by adding a portal pair. Which one
stays?

Recommendation: keep the additive portal rescue and drop the carving. Every layer reasons
on the promise that a committed object stays.

**Q4. Too few player towns.** Fail the run, or write a file with fewer seats?

Recommendation: fail with the count. A 3-seat file for a 4-player group is a broken
evening.

**Q5. Missing basic mine.** Fail the run, or warn and write?

Recommendation: fail, after a seed sweep measures how often it happens. The invariant says
every map, and a warning nobody reads makes it a wish.

**Q6. Gold cap.** Count player towns only, as the code does, or every town, as the spec
reads?

Recommendation: player towns only. Neutral towns are contested prizes, and the cap exists
to keep gold scarce near the starts.

**Q7. Likeness tolerance.** What band counts as inside the corpus?

Recommendation: the corpus 10th to 90th percentile per measure per type, as a report first.
Promote it to a sweep failure only after three seeds pass.

**Q8. Guard spacing for mine guards.** When a mine's guard spot is too close to another
guard, reject the mine spot, or drop the guard?

Recommendation: reject the mine spot and try the next. The spot search already walks
candidates in order, and an unguarded mine breaks the mine invariant.

**Q9. Stream independence.** Fix the shared stream in the sealed-zone and treasure layers
now, or with a shared stream function later?

Recommendation: later, with the shared function under P5. Both layers are out of scope,
and the byte-identical invariant holds today.

### Parked for `target-architecture`

- P1. Priors: one survey command, every statistic cached and versioned, a missing file
  raises with the command name. Removes the per-run corpus reads. (M11)
- P2. Catalog: a port handed in at the root, with no module-level accessors. (M12)
- P3. Tile art: computed by the Map file and the Preview, not by the terrain layer. (M13)
- P4. Layers: typed results in place of the shared workspace, and a zone-plan layer before
  vegetation so a run can stop after it. (M14)
- P5. Random stream: one function of seed, salt and region id, called by every layer.
  (M10)
