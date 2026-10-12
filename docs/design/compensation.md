# Fairness by compensation

Disclosure: I read the gameplay placer, the claimed-value reading, the loot step and
`global-placement.md` before this note's method loaded. Their design decisions sit in 1b
as claims. I also measured the claimed-value gaps on today's maps before writing the
note, since the size of the gap decides the design.

## 1. Problem

A player who starts behind on a generated map reaches less value before the other players
than the best-placed player does. Today the placer tries to prevent that by weighing every
spot by how it spreads the players' reach of each object family. That weighing makes the
placer hard to change, and it buys nothing measurable: on four 72 maps with four players,
the worst player's share of the best player's claimed value at 20 days is 0.26, 0.70, 0.41
and 0.71 with it, and 0.18, 0.75, 0.37 and 0.61 without it.

The person who feels it is the map's player who starts behind, and the maintainer who has
to reason through the placer's ranking to change anything.

**Done looks like this.**

- The placer stands every object of no player for coverage and the full plan. No per-player
  term ranks its spots. It places at least as many objects as today, and no open tile sits
  further from its nearest gameplay object than today.
- Each player whose claimed value at 20 or 40 hero-days falls below the bar gets one
  artifact prize. The player reaches the prize first, within 20 days, its guard counted.
  The bar is the corpus median share for the map's size: 0.46 at 20 days and 0.38 at 40
  days on 72 maps (A1).
- A player still below the bar after its prize shows in the report with its gap in gold.
- On 72 maps with four players, seeds 1 to 10, and 144 maps with six players, seeds 1 to 4,
  the median worst share sits at or above the corpus median, and the 144 map still
  generates within the speed budget (A7).

**Out of scope.**

- Start access. On seed 2 at 144, one player reaches 545 rewards within 5 hero-days and
  another reaches 32. That player claims 17 times the worst player's value, a gap of
  about 780,000 gold, which no single prize closes. It needs its own note.
- The 14-day basic mine promise and the guard that keeps it even between players.
- The rare mines' way and the neutral towns' siting rule (A9).
- The artifact guard study: whether a prize's guard follows its tier the way the corpus
  does.
- Roads.

## 1b. Claims

1. "A disadvantaged player should receive an artifact prize in compensation rather than
   shaping the whole map for them." The user.
2. "It would greatly simplify placement." The user.
3. "I would prefer less fairness but no dead spot on the map and more objects placed." The
   user.
4. Fairness uses the same hero-days effort as the rest: travel plus the monster in front.
   The user.
5. "It would make sense to balance value for the first 40 days." The user.
6. "A dragon can make sense for a very worthy artifact like the Armageddon blade." The user.
7. At 20 and at 40 hero-days, the worst player's claimed value is at least 0.8 of the best
   player's. `global-placement.md`, invariant 6 and A15.
8. A player claims an object when no other player reaches it sooner, guards included. Two
   players reaching it on the same day both claim it. `global-placement.md`, R19.
9. The placer ranks a spot first by how it moves the worst player's share.
   `global-placement.md`, slice 8.
10. The prize is worth about the gap and is guarded from the artifact guard record. My
    proposal, approved by the user.
11. A promised mine takes the lowest guard that keeps the players even on its resource.
    `global-placement.md`, R21.

## 2. Parts and concepts

### Level 1: parts

1. **Placement.** Stands the planned objects where they cover the land and fill the plan.
   It owns where each object of no player stands. It never knows which player is ahead.
   It hands a map full of objects to the later steps.
2. **Claim reading.** Reads, on any map, the value each player claims first within a horizon
   of hero-days. It owns the meaning of "claims first". It never knows how an object came to
   stand. It hands the claims to Compensation and to the Report.
3. **Compensation.** Decides which players are behind and how big a prize each gets. It owns
   the bar and the prize's tier. It never knows where a prize stands. It hands one prize
   order per behind player to Prize standing.
4. **Prize standing.** Stands one artifact and its guard where its player reaches it first.
   It owns the ground a prize may take. It never knows why the prize exists. It hands the
   standing prize back to the map.
5. **Report.** Prints the shares before and after compensation, beside the corpus, and the
   players still behind. It owns nothing the map depends on.

Flow. Placement and every later step that adds a reward finish the map's rewards. Claim
reading reads the claims once. Compensation turns them into prize orders. Prize standing
stands each order. Claim reading reads the finished map a second time for the Report.

In plain words: the map is laid out for coverage first. Once every reward stands, the
generator counts what each player can grab before the others. A player who falls well
behind gets one artifact near home, behind a monster that suits the artifact.

### Level 2: concepts

**Placement**

| Concept | Owns | Never knows |
|---|---|---|
| Spot rank | The order of candidate spots by band, distance from standing objects and target days | Players' claims |
| Guard draw | The guard an object draws from its family's record | The spot and the players |

**Claim reading**

| Concept | Owns | Never knows |
|---|---|---|
| Player effort | Per player, the hero-days to visit a tile, its guards counted | Rewards and values |
| Reward value | One object's gold-equivalent value | Players |
| Claim | One reward's value with each player's days to it | How either was measured |
| Claimed value | Per player, the value it claims first within a horizon | The map |

Claim is a shared value type. Reward value is a read-only reference that every part may
consult.

**Compensation**

| Concept | Owns | Never knows |
|---|---|---|
| Bar | The share below which a player is behind, per horizon and map size | Players and prizes |
| Deficit | Per player, the gold it lacks to reach the bar at its worse horizon | Prize tiers |
| Prize choice | The cheapest artifact tier whose value covers the deficit, the top tier when none does | Where the prize stands |

**Prize standing**

| Concept | Owns | Never knows |
|---|---|---|
| Prize guard | The guard level a prize of a tier stands behind | The player |
| Prize ground | The tiles where the player reaches the prize strictly first within 20 days, the prize's guard counted | The prize's tier |
| Prize stand | Standing the artifact and its guard on the most open tile of the ground | Why the prize exists |

**Report**

| Concept | Owns | Never knows |
|---|---|---|
| Share row | The worst share at each horizon, before and after, beside the corpus spread | Prizes |
| Behind list | Each player still below the bar, with its gap in gold | How the bar was set |

## 3. Invariants

1. Each player receives at most one prize per map. **Owner:** Prize choice.
2. No player at or above the bar at both horizons receives a prize, and no prize goes past
   the top tier. **Owner:** Prize choice.
3. A prize stands where its player reaches it strictly before every other player and
   within 20 days, its guard counted. **Owner:** Prize ground. Upheld by Prize stand.
4. A prize keeps every walkable tile reachable, and its guard adds less than a day to any
   player's way to any tile. **Owner:** Prize stand, through Player effort. Revised, see M2.
5. Spot rank holds no per-player term for an object of no player. **Owner:** Spot rank.
6. The same seed gives the same prizes. **Owner:** Compensation, through its seeded draw.

## 4. Forces and patterns

**Forces.**

- F1. The placer's per-player ranking costs complexity and buys no share. Remove it.
- F2. The corpus and the generated maps must be read the same way. One Claim reading
  serves both.
- F3. Every step after the placer adds rewards: pockets, treasure, sets, free piles. The
  claims are only final once the last of them has run.
- F4. The bar is a corpus number per map size and may be retuned.
- F5. A prize stands under the same ground, footprint and reach rules as any object.
- F6. The 144 map is close to its speed budget.

**Between parts.** A sequence of stages with one value handed along (F3). Compensation runs
as its own stage after the last reward step and before roads. The claims are the value it
reads.

**Inside parts.**

- Spot rank: a plain sort key with one term fewer (F1).
- Claim reading: the existing pure functions (F2).
- Bar: a plain value per size, loaded with the priors (F4).
- Deficit, Prize choice, Prize ground, Prize guard: plain functions. No force asks for
  variants.
- Prize stand: the existing single-object standing with a guard (F5). No new pattern.
- Claim reading runs once per pass, and Prize ground reads the same effort maps (F6).

No role. The user asked for an artifact. A force for other prize kinds, such as a bank or a
pile, does not exist today.

**SOLID.** Every Owns reads without "and". Adding a prize kind would add a concept and a
line in Prize choice, which is acceptable without a role today. No variants, so Liskov and
interface segregation do not apply. Compensation depends on Claim reading's values, never
on Placement.

**Claims.**

- 1, 2 and 3: derived from F1 and F3.
- 4: derived. Player effort counts the guard days.
- 5: derived. The horizons are 20 and 40 days.
- 6: derived. Prize guard pairs a stronger guard with a higher tier.
- 7: rejected. The corpus 72 maps give a median of 0.46 at 20 days, with the upper quartile
  at 0.70. A bar of 0.8 sits above three quarters of hand-made maps. The bar is the corpus
  median (A1).
- 8: derived. Claim reading keeps it.
- 9: rejected by F1.
- 10: reshaped. Gaps to the best player run from 30,000 to 780,000 gold, and the top tier is
  worth 20,000. The prize covers the deficit to the bar, not the gap to the best, and one
  prize is the limit (A2).
- 11: out of scope. The promise keeps its own guard rule.

**Open lookups.**

- L1. Can the single-object standing with a guard be used after the gameplay step, over the
  finished map? Decides Prize stand.
- L2. Do roads change hero-days? Decides where Compensation sits in the sequence.
- L3. Where does the tier-to-guard pairing live today? Decides Prize guard.
- L4. Which parts of the placer use the per-player reach besides objects of no player?
  Decides how much Placement can drop.

## 5. Mapping onto the existing system

Revision log.

- M1. Section 1, out of scope: neutral towns and rare mines keep their per-player rule. L4
  found the spread code in their ranks too.
- M2. Section 3, invariant 4, and Prize stand: slice 1 found that a guard beside a prize can
  close no passage and still sit across the shortest way to rewards beyond it. Seed 3 at 72
  moved other rewards a day further. Prize stand now owns the rule and asks Player effort for
  the detour every prize guard adds, under one day. It stands the prize on its own tile
  search, since the gameplay sites hold no detour check.

**Parts.**

| Part | Verdict | Where |
|---|---|---|
| Placement | Reshape | `core/steps/gameplay/siting.py`. Objects of no player rank by `lexsort((r, target, -gap, off, spread))` at lines 461 to 469. Spread comes from `Reach.cost`. |
| Claim reading | Exists | `core/reading/claimed.py`: `Claim`, `claimed`, `owner_maps`, `claims_of` |
| Compensation | New | `core/steps/compensation/`, with `step.py` and `result.py`, a stage named `compensation` in `cli/steps.py` between `scatter` and `roads` |
| Prize standing | New | Inside the compensation step, on the existing standing code |
| Report | Reshape | `cli/readings.py` `value_reading` prints the shares. It gains the before row and the behind list from the step's result. |

**Concepts.**

| Concept | Verdict | Where |
|---|---|---|
| Spot rank | Reshape | `siting.py:461`. The spread term goes. A tree copy without it placed the same counts within one object at 72 and 144, and left 0.3% of open tiles 6 or more tiles from an object at 144 against 0.9% today (A6). |
| Guard draw | Exists | `core/placement/guard_draw.py` |
| Player effort | Exists | `core/reading/effort.py`, `EffortMap.visit` |
| Reward value | Exists | `core/reading/value.py`, `ARTIFACT_VALUE`: 2,000, 5,000, 10,000 and 20,000 per tier |
| Claim, Claimed value | Exists | `core/reading/claimed.py` |
| Bar | New | A prior beside the other corpus priors in `data/pp/`, mined by the corpus tools, one value per standard size and horizon |
| Deficit, Prize choice | New | `core/steps/compensation/` |
| Prize guard | Reshape | `core/steps/loot/pocket_plan.py:10` pairs guard level to tier for pocket caches. Compensation needs tier to guard. The table moves to `core/planning/guarding.py`, which both steps read. |
| Prize ground | New | `core/steps/compensation/`, over the effort maps Claim reading built |
| Prize stand | New, revised, see M2 | `core/steps/compensation/stand.py` `PrizeStand` stands the artifact and its guard on the finished map and asks `EffortMap.detour` in `core/reading/effort.py` for each guard. The artifact comes from `Catalog.random_artifact(tier)`, so the catalog gains nothing. |
| Share row, Behind list | Reshape | `cli/readings.py` |

**What the existing system has that the design lacks.**

- `Reach` in `gameplay/reach.py` and the per-tile spread codes. Waste for objects of no
  player. The neutral towns' "widens no gap" filter (`siting.py:453`) and the rare mines'
  rank (`siting.py:471`) still read them, so `Reach` stays for those two (A9).
- `_even_guard` for the promised mines. A concept outside this note: the promise.
- The uneven-tiles-last rank of R22 goes with the spread, since nothing is uneven any more.

**Claims against the code.** The code follows 4, 5, 8 and 11 today. It follows 9 only
partly: R22 ranks uneven tiles last instead of first by share. The design keeps 4, 5, 8 and
11 and drops 9.

**Lookups resolved.**

- L1: open. It becomes A8.
- L2: `core/reading/routes.py` has no road term. Roads leave hero-days unchanged, so
  Compensation may sit before roads (A3).
- L3: `pocket_plan.py:10`, guard to tier only.
- L4: neutral towns and rare mines, M1.

## 6. Slices

1. **One prize for a player far behind.** Claim reading, Bar as a constant for 72 (0.46 and
   0.38), Deficit, Prize choice, Prize guard, Prize ground, Prize stand, a minimal Report
   line. Done when: on 72 with four players, seeds 1 to 4, every player below the bar
   receives one prize it claims first within 20 days, the Report prints each prize and
   each player still behind, and `make check` and `make sweep` pass. Seed 1 shows the
   behind list, since its three trailing players lack 46,000 to 56,000 gold each at 20
   days.
2. **Placement without the spread.** Spot rank. Done when: on 72 with four players, seeds
   1 to 10, and 144 with six players, seeds 1 to 4, the map places at least as many objects
   as today, the share of open tiles 6 or more tiles from an object does not rise, the
   median worst share after compensation is at or above the corpus median, and the 144 map
   generates within the speed budget.
3. **The bar per map size.** Bar mined from the corpus per standard size into `data/pp/`.
   Done when: the 36, 108 and 144 maps read their own bar, and the Report prints it.

Each slice passes `make check`, updates the docs it renames, and is committed on main. The
first slice also revises `global-placement.md`: invariant 6, A15 and slice 8 point to this
note.

## 7. Assumptions

1. **Assumption:** the corpus median share at each horizon is the bar a fair map should
   meet. **Decided:** the bar is 0.46 at 20 days and 0.38 at 40 days on 72 maps, and the
   corpus median of each standard size elsewhere. **Basis:** 71 corpus 72 maps read 0.46
   [0.31, 0.70] at 20 days and 0.38 [0.23, 0.55] at 40 days. R19 reads 0.25 and 0.27 on
   corpus 144 maps, many of them scenarios. A15's 0.89 does not hold on today's reading.
   **If wrong:** Bar, invariant 2, slice 1 and 2 done-whens.
2. **Assumption:** one prize per player is the right limit, and the gaps a prize cannot
   close come from start access. **Decided:** one prize, sized to the deficit to the bar,
   capped at the top tier. **Basis:** on 72 with four players, seed 3 needs one prize of
   10,500 gold and seeds 2 and 4 need none. Seed 1 lacks 46,000 to 56,000 per player. On
   seed 2 at 144, the best player reaches 545 rewards within 5 days and the worst 32. Seed
   1 at 72 has no start-access reading yet. **If wrong:** Prize choice, invariant 1, the
   start-access note.
3. **Assumption:** roads leave hero-days unchanged, and no step after scatter adds a reward.
   **Decided:** Compensation runs between scatter and roads. **Basis:** `routes.py` has no
   road term. The step list in `cli/steps.py` ends with scatter then roads. **If wrong:**
   the flow in section 2.
4. **Assumption:** the pocket caches' guard-to-tier pairing suits a prize. **Decided:**
   Prize guard inverts it. **Basis:** `pocket_plan.py:10`, and claim 6. **If wrong:** Prize
   guard, after the artifact guard study.
5. **Assumption:** a behind player has ground it reaches first within 20 days with room for
   an artifact and its guard. **Decided:** Prize ground takes 20 days first, then 40, and a
   player with no ground shows in the behind list. **Basis:** on seed 2 at 144, the worst
   player still claims 35 rewards first within 10 days. **If wrong:** Prize ground.
6. **Assumption:** the spread term buys no coverage and no fairness. **Decided:** slice 2
   removes it. **Basis:** a tree copy without it placed the same counts within one object
   at 72 and 144, and its worst shares at 72 match today's within the noise of four seeds.
   **If wrong:** Spot rank keeps the spread as its last tie-break.
7. **Assumption:** one more claim reading fits the 144 speed budget. **Decided:** the
   compensation pass reads the claims once and reuses its effort maps for Prize ground.
   **Basis:** none. The 144 map runs 57 to 60 seconds of CPU against its budget, and
   slice 2's removal of the spread saves some of it. **If wrong:** Claim reading reads
   only the tiles within 40 days.
8. **Assumption:** the zone sites can be rebuilt over the finished map to stand one object.
   **Decided:** Prize stand rebuilds the site of the zone that holds the chosen tile.
   **Basis:** `gameplay/step.py:475` builds a site from its zone record alone. **If
   wrong:** Prize stand uses the single placement the pocket caches use, with an explicit
   guard.
9. **Assumption:** neutral towns and rare mines may keep their per-player rule for now.
   **Decided:** `Reach` stays for those two. **Basis:** a town carries no value in the
   claimed reading, and the rare mines follow each player's way. **If wrong:** a later
   slice removes `Reach` for them.
