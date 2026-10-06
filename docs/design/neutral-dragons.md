# Neutral dragons as guards and rewards

Disclosure: before this note I had read the guard toll, the fair guard, the reward tiers,
the landmark step and the catalog's creature level. Their decisions are claims in 1b.

## 1. Problem

A player never meets an azure, crystal or rust dragon on a generated map. Hand-made maps
put one in front of their best prize on 10 of the 159 corpus maps, and the game's own boxes
can pay one. Generated maps stop at level 7 for both guards and rewards.

Done looks like this:

- Every generated map with a dragon dwelling shows a neutral dragon in front of it, and
  the effort report prices that prize past every level 7 guard.
- In the top band, about one creature reward in five pays a single neutral dragon.
- Banning a dragon or disabling its mod removes it from guards and rewards alike.
- The same seed gives the same map.

Out of scope:

- The faerie dragon, level 8, whose wild stack is weaker than a level 7 stack (A3).
- Dragons in front of other top-band prizes in cut-off places. It is parked as a later
  slice.
- The seer hut reward. It paid level 1 creatures only, and now pays levels 4 and 5, so a
  stack is worth about as much as its gold.

### 1b. Claims

1. A fair guard tries levels 1 to 4 and no higher (global-placement.md, decision 12).
2. The dragon dwelling stands behind a guard of the top level, 7 (landmark step).
3. A creature's guard level is its game level capped at 7 (catalog adapter).
4. A reward tier draws a stack from a list of levels with one count range for all of them
   (effort priors).
5. The toll table holds 8 entries, levels 0 to 7 (effort priors).

## 2. Parts and concepts

### Level 1: parts

1. **Creature roster.** It knows every creature: its game level, its strength and the size
   of its wild stack. It never knows where a creature stands. It answers the other parts.
2. **Guard scale.** It owns the ladder of guard strengths and the hero-days each one costs.
   It never knows which prize a guard protects. It hands a tier's creatures and toll to
   guard choice and to map reading.
3. **Guard choice.** It decides which tier stands in front of which prize. It never knows
   how a tier turns into a creature. It asks the scale for the tier's creatures.
4. **Reward packs.** It owns what a box pays in creatures per band. It never knows where
   the box stands. It asks the roster for the creatures of a level.
5. **Map reading.** It reads each guard on a map, hand-made or generated, onto the scale.
   It never knows how the guard was chosen. It hands the toll to the effort measure.

Flow: the roster feeds the scale and the packs. Guard choice picks a tier, then draws one
creature from that tier with the map's seeded draw. Map reading reads every guard back
onto the same scale, so the effort a player pays matches the guard the map shows.

### Level 2: concepts

Creature roster, a read-only reference every part consults:

| Concept | Owns | Never knows |
|---|---|---|
| Game level | a creature's level, 1 to 10 | the guard scale |
| Neutral dragon | the walking creatures of game level 10 | rewards |
| Enabled creature | whether mods and bans allow a creature | guard choice |

Guard scale:

| Concept | Owns | Never knows |
|---|---|---|
| Guard tier | the rank 0 to 8 of a guard's strength | which prize it guards |
| Toll | the hero-days to beat a guard of each tier | the creatures |
| Tier pool | the creatures that may stand at one tier | the toll |

Tier 1 to 7 holds the random monster of that level. Tier 8 holds the enabled neutral
dragons.

Guard choice:

| Concept | Owns | Never knows |
|---|---|---|
| Fair guard | the weakest tier from 1 to 4 that keeps the players even | tier 8 |
| Top-prize guard | tier 8 in front of the prize the homes reach last | fairness |
| Guard draw | one creature from a tier's pool by the seeded draw | the prize |

Reward packs:

| Concept | Owns | Never knows |
|---|---|---|
| Pack | one level, its count range and its weight | the band |
| Band grant | the packs a band's creature reward draws from | the box's place |

Map reading:

| Concept | Owns | Never knows |
|---|---|---|
| Guard tier reading | the tier of a guard object on a map | how the map was made |

## 3. Invariants

1. Every guard on a map reads at a tier from 0 to 8, and its toll counts in effort.
   Owner: guard tier reading. Upheld by: tier pool.
2. A tier pool is never empty for a tier guard choice asks for. With every neutral dragon
   disabled, tier 8 falls back to the tier 7 pool (A7). Owner: tier pool.
3. A neutral dragon pack pays exactly one creature. Owner: band grant, which rejects a
   pack whose count range breaks the cap.
4. A disabled or banned creature never stands as a guard or pays as a reward. Owner:
   enabled creature.
5. A fair guard never picks above tier 4. Owner: fair guard.
6. Every draw comes from the map's seeded random source. Owner: guard draw.

## 4. Forces and patterns

Forces:

- The creatures at a tier vary with mods and bans. That is data, a pool per tier.
- The toll and the packs are numbers the user tunes and the corpus mines. That is data, a
  table in the priors.
- One rule decides where a dragon stands today. No variant exists, so it is a plain
  function.
- Tests must build a pool without a VCMI install. The roster stays behind the existing
  catalog port.

Patterns:

- Between parts: a read-only reference (the roster) and plain values handed along (tier,
  toll, pack). The force is the mod and ban filter, which lives in one place.
- Inside parts: no pattern. Tier pool and pack are value types. Guard draw is a function.

Claims:

- Claim 1 holds, re-derived: a tier 6 guard costs 28 days, past the last band edge of 22,
  so a dragon is never the weakest tier that evens the players (A2).
- Claim 2 is rejected: the top prize takes tier 8 when a dragon is enabled.
- Claim 3 is rejected: game level 10 reads at tier 8. Levels 7 and 8 read at tier 7.
- Claim 4 is rejected: one count range cannot serve a stack of three level 6 creatures and
  a single dragon. Each pack carries its own range and weight.
- Claim 5 is rejected: the toll grows to 9 entries.

SOLID: every Owns reads without "and". A new dragon from a mod joins a pool and changes no
code. Guard choice depends on the tier, never on the creature.

## 5. Mapping onto the existing system

Revision log: none.

- **Creature roster: Exists**, in the catalog port. `monsters(level)` matches the game level
  exactly (`vcmi/catalog/objects.py:334`), so `monsters(10)` already returns the three
  dragons through the mod and ban filter (`vcmi/catalog/adapter.py:130`).
- **Guard tier reading: Reshape.** `creature_level` caps at 7
  (`vcmi/catalog/adapter.py:139`). It becomes 8 for game level 10. The port's docstring
  says 1 to 7 (`core/catalog.py:153`). Route and family readers call it
  (`core/reading/routes.py:187`, `core/reading/families.py:96`), so effort picks up tier 8
  with no change there. Place content counts a named monster as fixed, without a level
  (`core/reading/content.py:71`), so the corpus prize guard spread stays random monsters
  only. That matches the design.
- **Toll: Reshape.** `DEFAULT_TOLL` holds 8 entries (`core/priors/effort.py:12`) and the
  mined `data/pp/effort.json` copies it. Both gain a ninth entry, 70 days (A1).
- **Tier pool: New**, as a catalog port method that returns the identities of a tier.
  `guard(level)` returns one random monster clamped to 7 (`vcmi/catalog/adapter.py:147`).
  About ten callers place random monsters through it and stay unchanged.
- **Guard draw: New**, beside the guard placement code in `core/placement/`.
- **Top-prize guard: Reshape.** The landmark step guards the dragon dwelling at
  `TOP_TIER = 7` (`core/steps/gameplay/landmark.py:27`, `:150`). The site's guard front
  turns a level into one creature (`core/placement/site.py:541`). It draws from the tier
  pool instead.
- **Fair guard: Exists.** Its top is `min(FAIR_GUARD, len(toll) - 1)`
  (`core/steps/gameplay/siting.py:234`), so a longer toll leaves it at 4.
- **Pack and band grant: Reshape.** `RewardTier` holds `levels` and one `creatures` range
  (`core/priors/effort.py:22`). `draw_reward` picks a level uniformly
  (`core/placement/rewards.py:31`). `creatures_of` reads levels 1 to 7 only
  (`core/placement/rewards.py:26`). Packs replace the pair.
- The system has the seer hut tier, which pays 5 to 20 level 1 creatures because its
  `levels` defaulted to `(1,)` (`core/placement/rewards.py:19`). It is a concept the design
  did not need. It now draws levels 4 and 5: 5 to 20 of them are worth about 1,500 to
  16,000 gold, against its 3,000 to 15,000 gold reward. The pandoraBox tier had the same
  default. It now draws levels 2 and 3: 3 to 10 of them are worth about 300 to 7,500
  gold, against its 500 to 5,000 gold reward.

## 6. Slices

1. Dropped: the dragon dwelling already stands behind a guard. **The dragon dwelling
   stands behind a neutral dragon.** It touches game level, guard
   tier reading, toll, tier pool, guard draw and top-prize guard. Done when: on seeds 1 to
   10 at size 72, every map with a dragon dwelling shows a neutral dragon in front of it,
   the effort report prices it at 70 days or more, and `make check`, `make sweep` and
   `make golden` pass.
2. **Top-band boxes can pay one neutral dragon.** It touches pack and band grant. Done
   when: over seeds 1 to 10, about one top-band creature reward in five pays one dragon,
   and banning `azureDragon` removes it from every reward.
3. Parked: dragons in front of other top-band prizes in cut-off places, at the corpus rate.

## 7. Assumptions

1. **Assumption:** a tier 8 guard costs 70 hero-days. **Decided:** the toll's ninth entry
   is 70. **Basis:** an average wild stack of rust, crystal and azure dragons is 1.2, 1.8
   and 3.7 times an average level 7 stack by the game's AI value. The toll grows about 1.6
   times per tier (28 to 45). **If wrong:** toll. The cost is low: anything past 22 days is
   already top band.
2. **Assumption:** the fair guard never needs a dragon. **Decided:** the fair guard stays at
   4. **Basis:** band edges 8, 13 and 22 against a tier 6 toll of 28. **If wrong:** fair
   guard, claim 1.
3. **Assumption:** the faerie dragon belongs at tier 7. **Decided:** game levels 7 and 8 read
   at tier 7. **Basis:** a wild faerie stack is 0.9 times a level 7 stack. **If wrong:**
   guard tier reading.
4. **Assumption:** the game picks a wild stack of 1 to 3 for a named dragon written with
   no count. **Decided:** the map writes no count. **Basis:** the game's creature table
   gives 1 to 3. **If wrong:** toll.
5. **Assumption:** one creature reward in five suits a dragon in the top band. **Decided:**
   the dragon pack weighs 1 against 2 for each of levels 6 and 7. **Basis:** none. The
   corpus files drop reward contents. **If wrong:** band grant.
6. **Assumption:** the map writer writes a named monster that the game loads. **Decided:**
   no writer change. **Basis:** the corpus maps carry 23 named neutral dragons through the
   same writer. **If wrong:** slice 1.
7. **Assumption:** with every neutral dragon disabled, a level 7 guard is the right
   stand-in. **Decided:** tier 8 falls back to the tier 7 pool. **Basis:** the top prize
   keeps today's guard. **If wrong:** tier pool.
