# Mine count on the corpus curve

Disclosure: before this note I read the quota code, the placement pass that calls it and the
promise allocator, while timing and counting mines. The decisions they carry are listed as
claims in 1b.

## 1. Problem

A player on a large generated map finds far more mines than a mapmaker would place. A
2-player map of size 144 holds about 93 resource mines, against about 27 on a corpus map of
the same size and player count. Small maps look right, because one corpus rate per tile
happens to fit size 72.

Done means that for 2-player maps at sizes 36, 72, 108 and 144, the mean count of resource
mines over five seeds is within 20% of the corpus curve at the generated map's land area and
player count. Every player still reaches each basic resource within the promise, with no new
promise warning.

Out of scope:

- Windmills, water wheels, mystical gardens and magic springs. They follow land area alone
  in the corpus (exponent 0.98, no player effect), which the per-tile rate already models.
- Dwellings, banks and visitables. They may show the same overshoot. Nobody has measured it.
- Which resource each mine yields, and where it stands.
- The PortalStep crash on seed 2 at size 144.

## 1b. Claims

1. The count of each purpose is the area of each terrain times the corpus rate per tile of
   that terrain, times a density multiplier, then rounded at random. (quota code)
2. A purpose's count is split over its families in proportion to the corpus count of each
   family. (quota code)
3. Mines stood by the promise count against their family's share. (placement pass)
4. Windmills and the other weekly producers are mine families, split from the same mine
   count as the resource mines. (quota code, through the catalog's mine purpose)

## 2. Parts and concepts

### Level 1: parts

1. **Learning the curve** reads the corpus and states how the resource mine count of a map
   grows with its land area and its player count. It owns the fit. It never knows the
   generator. It hands the curve to Counting.
2. **Measuring a map** states a map's land area and player count, the same way for a corpus
   map and a generated one. It owns the definition of land. It hands the measure to Learning
   and to Counting.
3. **Counting** states how many objects of each group a generated map should hold: the
   resource mines by the curve, everything else by the rate per tile. It never knows where
   an object stands. It hands the counts to Splitting.
4. **Splitting** shares a group's count among its families by their corpus frequency, and
   takes off what already stands. It never knows how the count was reached.

Flow: Measuring feeds Learning once, when the corpus is mined. At generation, Measuring reads
the map, Counting turns the measure into a count per group, and Splitting turns each count
into families.

In plain words: learn from real maps how the number of mines grows with land and players,
measure the new map the same way, ask the curve how many mines it should have, then share
them out among the resources as real maps do.

### Level 2: concepts

**Learning the curve**

| Concept | Owns | Never knows |
|---|---|---|
| Resource mine | Which mine subtypes yield a resource daily: sawmill, ore pit, alchemist's lab, sulfur dune, crystal cavern, gem pond, gold mine. | The producers' weekly yields. |
| Count curve | The expected resource mine count at a land area and player count: a power law in both, with its fitted coefficients. | How the corpus was read. |
| Curve fit | Fitting the count curve to the corpus maps' counts and measures, in log space, corrected for the bias of the log mean. | How the curve is used. |

**Measuring a map**

| Concept | Owns | Never knows |
|---|---|---|
| Land area | The count of land tiles over every level: tiles neither water nor rock. | Whether the map is corpus or generated. |
| Player count | The players the map is made for. | Teams and towns. |

**Counting**

| Concept | Owns | Never knows |
|---|---|---|
| Group | A set of families counted by one rule: resource mines, producers, and each other purpose. | The families' frequency. |
| Count rule (role) | The expected objects of a group on a map. | Which variant answers. |
| Curve rule (variant) | The expected count from the count curve at the map's measure. | Terrain rates. |
| Rate rule (variant) | The expected count from each terrain's area times its corpus rate. For producers, the mine rate times the producers' corpus share. | Players. |
| Group rules | Which rule counts which group. | How each rule computes. |

The density multiplier and the random rounding apply to every rule's expectation, in the
quota that holds the group rules.

**Splitting**

| Concept | Owns | Never knows |
|---|---|---|
| Family share | Dividing a count among families by corpus frequency. | The count rule. |

Resource mine is a read-only reference both Learning and Counting consult. Land area and
player count form a shared value type, the map measure.

## 3. Invariants

1. Land is measured the same way on corpus maps and generated maps. Owner: Land area, the
   one definition both sides call.
2. The resource mine count never drops below the mines the promise stood. Owner: Family
   share, which already never removes a standing object.
3. The counts per group add up to the purpose total the map holds. Owner: Group rules, which
   cover every mine family exactly once, resource or producer.
4. The same seed gives the same map. Owner: Counting, which draws one random rounding per
   group in a fixed order.

## 4. Forces and patterns

Forces:

- The count rule varies by group: resource mines by the curve, the rest by the rate. Both
  exist today in one quota.
- The curve's coefficients come from the corpus and change when the corpus changes.
- The definition of land must not drift between the learning side and the generating side.
- Other purposes may move to a curve later. That is a growth force, not a variant present
  today. It gets no extra structure.

Patterns:

- Between parts: one value handed along. The curve is a frozen prior mined into `data/pp`
  like the other corpus statistics. The map measure is a plain value.
- Count rule: a strategy per group, chosen in the group rules table, because two rules
  coexist in one quota today. Adding a curve for dwellings later adds one table line.
- Curve fit: a plain function. No variation.
- Land area: one shared function both sides call. Answers the drift force.

Claims:

1. Re-derived for every group except resource mines, which take the curve.
2. Re-derived. The split by corpus frequency stays.
3. Re-derived. It upholds invariant 2.
4. Rejected for counting. Producers form their own group on the rate rule, because they
   follow area alone in the corpus. They stay mine families for the split and for placement.

Open lookups:

- Does a family whose standing objects exceed its share break the band plan? This decides
  whether invariant 2 needs new code.
- What land share do generated maps have? This decides whether done is reachable without
  retuning water.

SOLID check: each concept owns one thing. Adding a rule adds one variant and one table line.
Both rules are kinds of the count rule only. The role declares one question, the expected
count. The quota knows the role, not the variants.

## 5. Mapping onto the existing system

Revision log:

- 2b Counting, Rate rule: the producers' rate needs no new mined statistic. The pooled mine
  rate per terrain times the pooled producer share of mines equals the pooled producer rate.
  The per-family corpus counts are already in the effort priors.

Parts:

- Learning the curve: **New**. A miner in `corpus/mine/`, a loader and saver in `corpus/`,
  a frozen value in `core/priors/`, registered in the miner table and in the priors bundle.
  It follows the repo's pattern for corpus statistics.
- Measuring a map: **New** for land area, in `core/reading/`, the reader both sides share.
  `Terrain.is_land` already gives the tile test (`core/model/terrain.py:32`). Player count
  **Exists**: the corpus reads it from the `.h3m` (`corpus/mine/places.py:45`), and the
  generator holds it in `Demand.players` (`core/steps/gameplay/placer.py:32`).
- Counting: **Reshape**. `purpose_quota` (`core/steps/gameplay/quota.py:24`) counts every
  purpose by the rate and knows no groups. It gains the group rules. Its signature gains
  the map measure and the curve.
- Splitting: **Reshape**. `family_quota` (`quota.py:65`) splits a purpose over all its
  families. Mine families split per group instead: resource mines over the seven
  resources, producers over the producer families.

Concepts:

- Resource mine: **Exists** in part. `BASIC_MINE_RES` and `GOLD` in
  `core/steps/gameplay/economy.py:17` name the seven subtypes. The miner sits outside
  `core/steps/`, so the set moves to `core/reading/` where both sides import it.
- Count curve, Curve fit: **New**.
- Group, Group rules, Curve rule, Rate rule: **New**. The rate rule is today's computation,
  moved behind the role.
- Family share: **Exists**, `split` in `quota.py:41`.

The existing system has the density multiplier and the town count kept inside the town
quota. Both stay. The design missed neither.

Lookups:

- Standing objects beyond the share: `BandPlan.slots` (`core/steps/gameplay/bands.py:97`)
  takes each standing cell off the planned cells and plans nothing below zero. Invariant 2
  needs no new code.
- Generated land share: open. It is measured in slice 1. (A2)

Claim check: the existing system follows all four claims. The design keeps 1 to 3 and
rejects 4 for counting.

## 6. Slices

1. **Resource mines on the curve.** Touches all four parts. The miner fits the curve and
   writes it to `data/pp`. The quota counts resource mines by it, producers by the rate
   share. Done when the five-seed mean per size is within 20% of the curve, with no new
   promise warning, `make check` passes, and the goldens are updated.
2. **A readings line for the mine count.** Touches Measuring and the readings report. Done
   when `readings` prints each map's resource mine count beside the curve's expectation, so
   a drift shows without a scratch script.

## 7. Assumptions

1. **Assumption**: the player count drives the corpus mine count, not only the land.
   **Decided**: the curve takes both. **Basis**: the fit on 159 maps, log mines = -1.43 +
   0.49 log land + 0.51 log players, R² 0.72. Land alone explains less. **If wrong**: Count
   curve, Curve fit.
2. **Assumption**: generated maps have a land share near the corpus at each size.
   **Decided**: the curve reads the generated land as it stands. **Basis**: none for
   generated maps. Corpus shares are 0.91, 0.74, 0.78 and 0.57 at sizes 36 to 144. **If
   wrong**: done holds on the curve, but the counts may still look high or low beside corpus
   maps of the same size. That would be a water question, not a count question.
3. **Assumption**: corpus random mines and abandoned mines can be left out of the fit.
   **Decided**: the fit counts the seven resource subtypes only. **Basis**: they are 158 of
   about 4,900 resource mines, about 3%. **If wrong**: Curve fit undercounts by about 3%.
4. **Assumption**: a log-space fit with a mean correction gives the expected count.
   **Decided**: the intercept carries exp(σ²/2), about 4% at σ 0.29. **Basis**: the fit's
   residual spread. **If wrong**: Curve fit.
5. **Assumption**: changing the mine count changes every golden map and may move the
   promise warnings. **Decided**: slice 1 regenerates the goldens and checks warnings over
   the twelve-map sweep. **Basis**: the mine count feeds placement order. **If wrong**:
   nothing to re-derive.
6. **Assumption**: one mining run takes minutes, not hours. **Decided**: the fit runs inside
   `mine-stats` as its own named miner. **Basis**: loading the corpus and counting took
   about two minutes in the measurement. **If wrong**: Learning the curve gets its own CLI
   entry.
