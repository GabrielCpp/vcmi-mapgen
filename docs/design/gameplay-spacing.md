# Gameplay spacing

Status 2026-10-20: settled with the user. Slice 1 is built: the spacing prior and the
readings.

Disclosure: I read the gameplay step, its siting, picker, quota, bands, promise and turn
code before this skill loaded, while diagnosing seed 1028 at 144. Every design decision
that code carries and that this note touches is a claim in 1b. The parts and concepts in
section 2 come from the user's process and from the corpus measures. I checked each name
against the test "would I have named this without having seen the code?"

## 1. Problem

A player on a large map walks into the same object again and again in one corner. On seed
1028 at 144, windmills bunch near 55,56 and mercury labs near 105,95. The next copy of a
windmill is 11 tiles away at the median, and half of them have a copy within 10 tiles. On
the corpus maps of the same size, the next copy sits 25 tiles away and 7 in 100 have one
within 10. A magic well is worse: 71 in 100 have a copy within 10 tiles, against 5 in 100
on the corpus. The player gets three wells in one walk and none for the next two weeks.

Done looks like this to that player:

- Copies of one kind stand as far apart as they do on hand-made maps of the same size.
  Measured as the share of copies closer to their nearest copy than the corpus p10 of their
  kind (the copies crowded reading). The corpus maps of the same size and player count give
  0.095 [0.077, 0.165] at 144 and 0.075 [0.060, 0.114] at 72. Seed 1028 at 144 gives 0.301,
  and seeds 1 to 10 at 72 give 0.176. Done is the generated median inside the corpus
  quartiles at both sizes, with the kinds spaced reading inside its quartiles too. Kinds
  that the corpus bunches, such as some creature dwellings, stay bunched.
- Every player reaches a mine of each rare resource within 14 hero-days. A mine two players
  both reach serves both. No more rare mines stand than that cover needs, before the fill
  adds the corpus count.
- Counts per kind stay on the corpus, and no territory of 150 tiles or more stands empty.

Out of scope:

- Gates, home ways, shipyards, sea links and landmarks. They keep their order and rules.
- Neutral town spacing, which neutral-town-spacing.md owns.
- Gold's own rule: past 8 days from every home, contested within 3 days. A gold mine keeps
  that rule as a site filter and joins the fill like any other extra.
- The guard each object stands behind, which effort-reward.md owns.
- Fairness over 40 hero-days. The near-home mix is measured after the change, not designed
  around (A6).
- The per-player turn of extra rare mines along each player's way. It goes (5b row 6).

## 1b. Claims

From the user, 2026-10-19 and 2026-10-20:

1. Towns go first, the player towns especially.
2. Each player town gets a sawmill and an ore pit pair.
3. The minimum rare mines come next: one of each rare type within about 14 hero-days of
   each player, on the surface or underground.
4. Candidate spots come from base hero movement times 14 around each town, minus blocked
   spots. Each spot is priced by the walk to it.
5. A round robin on mine type per player picks the candidates. The per-player sets merge
   into (x, y, [players]). A shared spot collapses into one mine.
6. Every purpose goes into the zone quota, mines and weekly producers included.
7. Everything beyond the minimum is extra, and fills the remaining quota under a same-kind
   conditional spacing law.
8. The law comes from corpus histograms of nearest-copy distance per kind, normalised by
   each map's own count and land: u = nπx²/A, with F(x|n) = 1 − (1 − πx²/A)^n for random
   placement.
9. Families are fitted by AIC on the raw values, with chi-square on the bins as a check,
   and a non-parametric fallback when no family fits.
10. The fit uses every map size, and rare kinds pool so that no kind starves.

From the current code:

11. A slot's spot ranks by effort band first, then by distance to any gameplay object or
    home, then by target days, with a random tiebreak. (siting)
12. An object walks the zones in rank order and avoids copies of its kind only among the
    centres of one zone. (siting, picker)
13. The picker draws a slot's kind as it sites the slot, and weighs a kind down by 0.1 per
    copy within 10 tiles. (picker)
14. Extra rare mines are dealt to each player along their way out, with a soft
    same-resource check. (turn)
15. The promise stands mines before the map-wide pass and repairs after it. (allocate,
    step)
16. Each zone holds a share of dwellings, banks and visitables by its tiles, mines left
    out, and the cap is off by default. (placer)

## 2. Parts and concepts

### Level 1

1. **Homes** stands the towns and each player town's wood and ore pair. It owns where a
   player starts and the first supply. It never knows rare resources or spacing. It hands
   the standing towns and pairs to the cover and the fill.
2. **Resource cover** stands the fewest rare mines that bring every player each rare
   resource within 14 hero-days. It owns the candidate spots, their walk prices and the
   cover. It never knows the corpus counts or the spacing law. It hands the standing mines
   to the plan and to the fill as copies already on the map.
3. **Plan** says how many of each kind the map holds, and how many of each purpose each
   zone may take. It owns the counts and the zone shares. It never knows a spot. It hands
   the fill a roster of slots, each with its kind, band and target, and the room left per
   zone after homes and cover.
4. **Spacing law** says how likely a copy of a kind stands at a given distance from the
   nearest other copy, on a map of a given count and land. It owns the corpus fit per kind
   and the weight it gives a spot. It never knows zones, bands or players. The fill asks it
   for a weight.
5. **Fill** stands each slot of the roster on a spot. It owns the choice of spot. It never
   knows how the law was fitted or how the counts were drawn. It hands the finished map to
   the readings.
6. **Readings** measure the finished map against the corpus: nearest copies per kind,
   counts per kind, territory density, each player's reach to each rare resource and the
   near-home mix. It never changes the map.

Flow: homes, then cover, then plan, then fill. The law is fitted once from the corpus,
offline, and the fill consults it per spot. The cover acts a second time after the fill:
it reads each player's reach again and stands a mine only for a player the fill cut off.
The readings act last.

In plain words: put the towns down, then the fewest mines that give everybody every rare
resource close to home. Then decide how much of everything the map gets and how much each
area gets. Then put each object where hand-made maps would put the next copy of it.

### Level 2

**Homes**

| Concept | Owns | Never knows |
|---|---|---|
| Town spot | where each town stands | the pair, the cover |
| Supply pair | the sawmill and ore pit within reach of one player town | rare resources |

**Resource cover**

| Concept | Owns | Never knows |
|---|---|---|
| Candidate spot | a tile where a mine of one type fits, within the 14-day radius of a player, blocked spots removed | which player it will serve |
| Walk price | a player's hero-days to a candidate spot, its guard counted | the cover |
| Type round | the round robin that gives each type its pick of spots, so no spot carries two types | prices beyond the order they give |
| Shared spot | one spot of one type with every player that reaches it in time: (x, y, [players]) | how it was found |
| Cover | the fewest shared spots per type that reach every player | the corpus count of that type |
| Reach check | after the fill, the players who lost a type in time, and the one mine that restores each | spacing |

**Plan**

| Concept | Owns | Never knows |
|---|---|---|
| Purpose count | the corpus count of each purpose for the map's land and players | kinds within a purpose |
| Roster | each slot's kind, drawn from its purpose's corpus pool before any slot stands | spots |
| Zone share | the most of each purpose a zone may hold, by its share of the land | which kind |
| Band split | each slot's effort band and target days | spots |

**Spacing law**

| Concept | Owns | Never knows |
|---|---|---|
| Copy distance | the normalised distance u = nπx²/A of a spot to the nearest copy of its kind on its level | the fit |
| Kind fit | the fitted density of u for one kind, or for its family when the kind is rare | the map being generated |
| Random baseline | the density of u when copies stand at random: e^(−u) | the corpus |
| Spot weight | the fit over the baseline at a spot's u, never below a floor | zones, bands |

**Fill**

| Concept | Owns | Never knows |
|---|---|---|
| Open spot | a spot where the slot's kind fits, in its band, in a zone with room for its purpose | the law's fit |
| Spot draw | the seeded draw of one open spot, weighted by the spot weight, over the whole level | how weights are made |
| Footing | whether an object stands on a spot | the draw |

**Readings**

| Concept | Owns | Never knows |
|---|---|---|
| Nearest copies | per kind, each copy's u on the finished map, beside the corpus spread | how the map was made |
| Counts | per kind, the count per thousand land tiles, beside the corpus spread | spots |
| Territory density | visitables per hundred tiles per territory | kinds |
| Reach | each player's days to each rare resource | the cover's choices |

Shared values: `Kind` (type and subtype) and the level land area are plain value types every
part reads. The corpus is a read-only reference the plan and the law consult.

## 3. Invariants

1. **Every player reaches each rare resource within 14 hero-days, or a warning names the
   player and the resource.** Owner: reach check. The cover upholds it while standing.
2. **No spot carries two types in the cover.** Owner: type round.
3. **The cover stands no mine a smaller cover could do without.** A mine whose players are
   all reached by the other chosen spots of its type is dropped. Owner: cover.
4. **Each kind's count on the finished map equals its roster count, cover mines and pairs
   included.** Owner: roster. The fill upholds it by standing every slot or reporting it.
5. **No zone holds more of a purpose than its share.** Owner: zone share. The fill only
   draws open spots.
6. **The spot weight is never zero.** A spot the law dislikes stays possible, so no slot
   fails for want of a liked spot. Owner: spot weight.
7. **The same seed gives the same map.** Every draw comes from the step's seeded random.
   Owner: spot draw.
8. **The law is fitted on the same distance the readings measure.** Owner: copy distance.
   Both the fit and the readings call it.

## 4. Forces and patterns

Forces:

- F1. The corpus spread of u differs by kind. Windmills spread, some dwellings bunch. The
  law must follow each kind, not a single spacing.
- F2. Rare kinds have few corpus samples. A kind with ten copies cannot carry its own fit.
- F3. The count of a kind on a map changes the raw distance. Normalising by n and A makes
  maps of all sizes comparable.
- F4. The fit is offline and slow. The generator must stay under the 144 speed target.
- F5. The cover must be tested without the fill, and the fill without the corpus.
- F6. Which family fits a kind is a measurement, not a choice. A kind may fit none.
- F7. Random placement gives e^(−u). The fill can only shape the law through a weight on
  that baseline.

Between parts: one value handed along a sequence of stages (homes, cover, plan, fill),
because each part needs only what the earlier one stood (F5). The law is a read-only
reference built from a frozen prior file, like the other corpus priors (F4).

Inside parts:

- Kind fit: a plain value per kind holding its chosen family and parameters, or the KDE
  samples. The family choice happens offline in the miner (F6). The generator reads a
  density function and never knows which family it is. Families are variants behind one
  role, "density of u", chosen in the miner. Adding a family adds one fit and one entry in
  the miner's candidate list.
- Pooling: a kind with fewer than 30 corpus distances takes its family's pooled fit (F2,
  A4).
- Spot weight: a plain function, fit(u) over e^(−u), floored at 0.05 of the kind's largest
  weight (F7, A3).
- Cover: a plain function, greedy set cover by most players reached, then least gap
  between players, then days nearest the rare target (A2).
- Spot draw: a seeded weighted draw. Footing tries the drawn spot. A failed spot leaves the
  pool and the draw repeats (F5).

Claims:

- 1 and 2: re-derived. A player's first supply is a home concern and the cover needs to
  know which types remain.
- 3 and 4: re-derived from the problem's promise. The radius is a pre-filter only. The walk
  price decides.
- 5: re-derived. The round robin keeps two types from fighting over one spot. The merge
  plus cover is how shared spots collapse.
- 6 and 7: re-derived from F1 and the counts. The quota decides how many. The law decides
  where.
- 8: re-derived from F3 and F7.
- 9: re-derived from F6. AIC picks the family. Chi-square only flags a poor fit, which
  sends the kind to the KDE fallback.
- 10: re-derived from F2.
- 11: partly rejected. The band stays as the first filter because effort-reward.md settles
  it. The distance to any object leaves the rank. The zone share and the law carry what it
  did (A5).
- 12: rejected. It is the cause of the bunching.
- 13: rejected. The roster draws kinds before siting, so n is known when u is computed.
  The 0.1 weight answers the same force as the law.
- 14: rejected. Extra rare mines are plain fill.
- 15: re-derived as cover then reach check. The repair stands only what the fill broke.
- 16: rejected in part. Mines join the share, and the share is always on.

SOLID check:

- Single responsibility: each Owns reads without "and". The supply pair owns one thing per
  player town.
- Open/closed: a new family adds one fit in the miner. The generator does not change.
- Liskov: each family is a density of u only.
- Interface segregation: the fill asks the law one question, the weight of a kind at a
  spot.
- Dependency inversion: the fill's Never-knows names the fit.

Open lookups:

- L1. Does the promise's pricer give walk plus guard days per spot cheaply enough for a
  candidate set within 14 days? Waits: walk price.
- L2. Can the zone share take MINE without starving the weekly producers in small zones?
  Waits: zone share.
- L3. Does the picker draw a kind at siting time, so n is unknown then? Waits: roster.
- L4. Which distance does the repeat reading use? Waits: copy distance, invariant 8.
- L5. Does any later step read the turn's per-player rare slots? Waits: claim 14.

## 5. Mapping onto the existing system

Revision log:

- R1. Section 2, copy distance: L4 found the repeat reading uses Chebyshev distance
  (`core/reading/repeats.py:46`, `apart`). The law keeps the user's πx² with Euclidean x,
  and the reading gains a Euclidean u beside its Chebyshev shares. Invariant 8 holds on u.
- R3. Section 1, done, and 5b rows 5 and 11: the slice 1 baseline put the share of copies
  within 10 tiles inside the readings' corpus quartiles at 144 (0.165 against 0.133
  [0.100, 0.222]). The 0.07 target came from pooling every corpus map of 108 and up. The
  band from p10 to p90 of each kind passes windmills at a median u of 1.29 against 2.38.
  Done moves to the share of copies under their kind's corpus p10, which the readings print.
- R2. Section 2, roster: L3 confirmed the picker draws per centre while siting
  (`core/steps/gameplay/pick.py:93`). The roster is new, and the picker's near weight goes.
- R4. Section 2, fill: slice 2 first drew inside the band before any tile one band out. At
  seed 1028 at 144 the late band-1 slots saw about 264 open tiles in 1 or 2 zones, all near
  a copy, so copies crowded more (0.387) than before the slice (0.301). A tile where the
  kind would stand under its corpus p10 now ranks with the tiles one band further out.
- R5. Section 2, fill, and 5b row 4: gold mines took the contest line first, so 88% of them
  crowded at 144. Gold now draws by the spacing weight among the tiles the gold rule
  admits, an uncrowded tile first. The cost is the weakest player's claimed value at 72:
  within 10 days from 0.789 to 0.722, within 40 from 0.686 to 0.667 (0.756 before slice 2).
  The contest line first gives 0.805 within 10 but crowds 40% of gold at 72. Crowded first,
  then the contest gap, gives 0.694 and crowds 62% at 144. The user chose the spacing draw
  on 2026-10-20: coverage and the full plan come before fairness, which placement fixes later.
- R6. Section 6, slices 2 and 3, and 5b row 7: the close rare mines come from each player's
  rare slots, which keep their own ranking until slice 3 rewrites them. Slice 2 cannot move
  row 7 (0.256 at 144, 0.108 at 72 after it). Its at-or-below-0.05 target moves to slice 3.
- R7. Section 2, fill: gold stays out of the zone share, because the gold rule already
  decides where it may stand. Its strict pass keeps a tile only when every tile within the
  neighbourhood is admitted too, so the anchor cannot drift off the rule.

Parts:

| Part | Verdict | Where | Note |
|---|---|---|---|
| Homes | Exists | `gameplay/siting.py`, `gameplay/placer.py` towns and pairs | Matches. |
| Resource cover | Reshape | `gameplay/allocate.py` `keep_promise` | It stands per resource in a loop that serves whoever is behind. It has no round robin across types and no set cover. It runs before and after the pass (`step.py:242`, `step.py:247`). |
| Plan | Reshape | `gameplay/quota.py`, `gameplay/bands.py`, `gameplay/placer.py` `_cap` | Counts and bands match. The share leaves out MINE and is off by default (`placer.py:72`, `placer.py:236`). No roster. |
| Spacing law | New | `corpus/mine/spacing.py` writes `data/pp/spacing.json`, `corpus/priors.py` loads it, `core/priors/` holds the frozen value | |
| Fill | Reshape | `gameplay/siting.py` `_groups`, `_stand`, `_try` | It walks zone groups in rank order (`siting.py` `_groups`) and avoids copies only inside one group through `clear_first`. |
| Readings | Reshape | `core/reading/repeats.py`, `cli/readings.py` | Shares within 6 and 10 exist. No per-kind u beside the corpus. |

Concepts:

| Concept | Verdict | Where |
|---|---|---|
| Town spot | Exists | siting towns |
| Supply pair | Exists | `stand_pairs` in placer, 12-tile rule |
| Candidate spot | Reshape | `allocate.py` `offers`: every anchor of every site, with no radius pre-filter |
| Walk price | Exists | `allocate.py` `Pricer`, guard counted through `beside` (L1: it primes a batch per level) |
| Type round | New | `allocate.py` |
| Shared spot | New | `allocate.py` |
| Cover | New | `allocate.py`, replacing `_shared` for rare types |
| Reach check | Reshape | the second `keep_promise` call in `step.py:247`, limited to players the fill cut off |
| Purpose count | Exists | `quota.py` |
| Roster | New (R2) | `gameplay/roster.py`, drawing kinds with the picker's pools and no near weight |
| Zone share | Reshape | `placer.py` `_cap`: add MINE, always on |
| Band split | Exists | `bands.py` |
| Copy distance | New (R1) | `core/reading/repeats.py` |
| Kind fit | New | `corpus/mine/spacing.py` |
| Random baseline | New | `core/priors/` beside the fit |
| Spot weight | New | `gameplay/spacing.py` |
| Open spot | Reshape | siting groups become one map-wide pool per level, filtered by band and zone room |
| Spot draw | New | `gameplay/siting.py`, replacing the lexsort rank for slots of no player |
| Footing | Exists | siting `PASSES` |

What the existing system has that the design lacks:

- The turn along each player's way (`turn.py` `rare_slots`). Waste under this design: it
  answers fairness, which the user ranks after coverage (L5: only the placer reads it).
- The picker's near weight and `clear_first`. Waste: the law answers the same force.
- The distance to any object in the rank (`town_gap`). Kept out on purpose (A5).
- The guard step-down while a player stays behind (`keep_promise`). A concept the design
  missed: the cover tries the rare guard first, then one level lower, down to none. Added
  to walk price.

Claims against the code: 1, 2, 4 and 11 the code follows. 3 it follows without the radius.
5 it does not follow. 6 it follows except mines. 7, 8, 9 and 10 it does not follow. 12 to
16 the code follows and the design drops or reshapes as section 4 says.

The repo structure fits this change. No assumption about it.

## 5b. What must not move

Inputs: seed 1028 at 144 with 4 players, and seeds 1 to 10 at 72 with 2 players, read by
the readings tool on 2026-10-20 before any placement change. The corpus columns are the
readings' quartiles over the corpus maps of the same size and nearest player count.

| Receiver | Gets today | Enforced by | Before 144 | Before 72 | Holds when |
|---|---|---|---|---|---|
| 1. Player supply | windmill, mercury, gold and sawmill counts per 1k land | nothing | 0.736, 0.606, 0.389, 0.692 | not read | each inside the corpus p10 to p90 (0.155 to 1.122, 0.338 to 1.042, 0.340 to 0.864, 0.498 to 1.500) |
| 2. Player reach | each rare resource within 14 days | promise warnings | not read (A7) | not read (A7) | no new warning |
| 3. Total resource mines | the corpus curve | quota | 82, curve 78.9 | 32.5, curve 31.5 | within 10% of the curve |
| 4. Near-home mix | value claimed within 10 and 20 days | nothing | 0.713, 0.722 (corpus 0.561, 0.558) | 0.796, 0.748 (corpus 0.950, 0.925) | measured and reported (A6) |
| 5. Copies within 10 and 6 | the visitables' repeat shares | nothing | 0.165, 0.048 (corpus 0.133, 0.044) | 0.090, 0.045 (corpus 0.067, 0) | inside the corpus quartiles |
| 6. Way out | each player's way repeats a resource | nothing | 4 ways repeat | 1.5 | measured and reported (A8) |
| 7. Close rare mines | rare mines with one of their resource close | nothing | 0.267 (corpus 0) | 0.095 (corpus 0) | at or below 0.05 from slice 3 (R6) |
| 8. Territory F near 20,135 | visitables per 100 tiles | nothing | 4.31 with the share, 0 or 1 without | not read | at or above 4.31, and no territory of 150+ tiles with 1 or fewer |
| 9. Speed | the 144 target set 2026-10-10 | nothing | 57.2 s | 8.2 s | at or below 60 s at 144 |
| 10. Same seed, same map | golden hashes | `make golden` test | current hashes | current hashes | new hashes, regenerated once per slice, stable across two runs |
| 11. Spacing | copies crowded, kinds spaced | nothing | 0.301, 0.770 (corpus 0.095, 0.847) | 0.176, 0.801 (corpus 0.075, 0.857) | inside the corpus quartiles |

Rows enforced by nothing:

- Rows 1, 3, 5, 7, 8 and 11 become checks in the sweep through the readings, owned by the
  readings part. The design keeps them on purpose.
- Row 4 is let go: section 1 lists the near-home mix as out of scope, measured after.
- Row 6 is let go with the turn: section 1 lists it. The readings have no corpus spread for
  it, so A8 was false and the row is measured and reported.
- Row 9 stays a budget measured per slice. The readings time is wall time, not CPU.

## 6. Slices

Every done-when re-measures each 5b row on seed 1028 at 144 and seeds 1 to 10 at 72, and
states before and after.

1. **Law and reading.** Mine the spacing prior: per kind and level, u = nπx²/A on every
   corpus map with n ≥ 2, Euclidean x between object tiles. Fit exponential, Weibull, gamma
   and lognormal by AIC. Flag a chi-square p below 0.01 and fall back to KDE. Pool kinds
   under 30 samples by purpose. Add per-kind u to the readings beside the corpus spread.
   Take the 72 baseline. Touches: spacing law, readings. Done when the readings print each
   kind's median u for seed 1028 and the corpus spread, and no map changed (golden hashes
   equal).
2. **Map-wide fill under the law.** Roster before siting. Open spots pooled per level over
   every zone, band and zone room as filters. Seeded draw weighted by the spot weight.
   Picker near weight and `clear_first` removed. Zone share on by default with MINE inside.
   Touches: plan, fill. Done when rows 11 and 5 hold and rows 1, 3, 8, 9 and 10 hold.
   Row 7 moved to slice 3 (R6). Measured 2026-10-20, before then after: copies crowded
   0.301 to 0.155 at 144 and 0.176 to 0.092 at 72, inside the corpus quartiles. Copies
   within 6 0.048 to 0.024 and 0.045 to 0.019, inside. Copies within 10 0.165 to 0.032 at
   144, under the quartile, a fixed 10-tile reading at every size. Claimed within 10 at 72
   0.796 to 0.722 (R5). Rows 1, 3, 8 (4.90 per 100, no empty territory), 9 (48.2 s) and 10
   hold.
3. **Fewest rare mines.** Candidate spots in the radius, walk prices, type round, shared
   spots, cover. The turn's rare slots removed. Extras go to the roster. The reach check
   replaces the second promise pass. Touches: resource cover, plan. Done when rows 2 and 7
   hold, the cover stands no more mines per type than players, and every other row still
   holds.

## 7. Assumptions

1. **The weight fit over e^(−u) shapes the finished distribution close enough to the
   corpus.** Decided: the spot weight is that ratio. Basis: none; later copies change
   earlier nearest distances, and edges skew the baseline. If wrong: spot weight, slice 2
   done-when; replace the ratio with an iterative correction fitted on generated maps.
2. **Greedy set cover reaches the fewest spots on corpus-like maps.** Decided: greedy by
   most players, then evenness, then target days. Basis: at most 8 players, so greedy is
   within a factor ln 8 of the best and usually equal. If wrong: cover; an exact cover over
   the top candidates.
3. **A floor of 0.05 keeps every slot standing without undoing the law.** Decided: the
   floor. Basis: none. If wrong: spot weight, invariant 6.
4. **30 corpus distances are enough for a kind's own fit.** Decided: the pooling line.
   Basis: the corpus table shows the common kinds at 100 to 560 distances and the rare
   dwellings at 4 to 24. If wrong: pooling.
5. **Dropping the distance to any object from the rank leaves the map no more crowded.**
   Decided: the zone share and the law replace it. Basis: none. If wrong: open spot; the
   gap returns as a second weight.
6. **The near-home mix may move.** Decided: measured, not designed. Basis: the user, 2026-10-19.
   If wrong: fill; a band filter tightened near homes.
7. **Today's console shows no promise warning on seed 1028 at 144 or on seeds 1 to 10 at
   72.** Decided: slice 3 reads the warnings before its change. Basis: none measured; the
   readings tool silences the pipeline's console. If wrong: 5b row 2.
8. **Repeating ways may move freely.** Decided: row 6 is measured and reported. Basis: the
   readings print no corpus spread for it, so no target exists. If wrong: row 6 needs a
   corpus reading first.
9. **The roster's kind draw from the purpose pool keeps per-kind counts on the corpus.**
   Decided: the roster draws with the picker's corpus weights minus the near weight.
   Basis: the counts table, where most kinds sit within p10 to p90 today. If wrong: roster;
   per-kind counts from a corpus curve.
10. **The law per level with n split by land share is right for kinds on both levels.**
    Decided: n on a level is the kind's roster count times the level's share of land.
    Basis: none. If wrong: copy distance, kind fit.
