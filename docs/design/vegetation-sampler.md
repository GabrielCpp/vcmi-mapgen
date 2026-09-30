# Vegetation sampler as a role

Disclosure: I wrote the current code, so I saw the existing solution before this note.
The step subclass, the `grow.py` default and the shared canvas base class were in my context.
I checked each part and concept below against the test "would I have named this without
having seen the solution?". Every design decision that came from that context is a claim in
section 1b.

## 1. Problem

The person comparing vegetation algorithms feels this. Today the second algorithm is a
variant of the first one's step. The code that grows a level still falls back to the first
algorithm when nobody names one. Trying a third algorithm means picking which of the two to
copy or extend.

Done looks like this:

- `generate --vegetation gibbs` and `--vegetation field` pick the algorithm, and one
  vegetation step runs either.
- A third algorithm is one new package plus one line in the CLI's table. No other file
  changes.
- The Gibbs maps stay byte-identical. The golden hashes in `data/golden.json` do not move.
  The field maps stay identical too, checked against the hashes recorded before the change.

Out of scope:

- How either algorithm looks. The user still finds Gibbs and field hard to tell apart at a
  glance. That is a separate change to the field algorithm.
- The border seal, the zone plan and the island check.
- What the fitted corpus model contains.

## 1b. Claims

1. One `Sampler` role that the algorithms implement (my previous reply, from the user's
   "I would have expected the sampler to be an interface").
2. Gibbs and field each in their own package (my previous reply).
3. One vegetation step that takes a sampler, with the CLI choosing (my previous reply).
4. The shared zone canvas and the fitted model are composed, not inherited (earlier
   summary).
5. The role is an object with a method, not a bare function type (the user: "An object in
   other words").

## 2. Parts and concepts

### Level 1: parts

1. **Planting brief.** For each zone, which tiles may carry vegetation, which must stay open,
   which walls exist, and where growth should thicken. It never knows how the vegetation is
   drawn. It hands a brief per zone to Growing.
2. **Growing.** It decides which decorations stand where in one zone. It never knows the
   level, the other zones or the CLI. It hands the zone's placed objects and blocked tiles
   back to Finishing.
3. **Placement rules.** These are the hard rules every placement obeys: no blocking cell on
   the open web or a forbidden tile, and no open ground walled off. It never knows which
   algorithm asks. Growing consults it on every placement and every removal.
4. **Corpus model.** The fitted per-terrain statistics: categories, identities, intensities
   and target coverage. It is a read-only reference that Growing consults.
5. **Finishing.** It seals the zone borders, checks the level for walled-off pockets and
   publishes what later steps need. It never knows the algorithm.
6. **Assembly.** It picks the algorithm from the user's choice. It is the only part that
   names an algorithm.

Flow: Assembly picks an algorithm once, before the run. For each level, Planting brief writes
one brief per zone. Growing turns each brief into vegetation under the Placement rules,
drawing from the Corpus model. Finishing seals, checks and publishes.

### Level 2: concepts

**Planting brief**

| Concept | Owns | Never knows |
|---|---|---|
| Zone brief (value) | The tiles one zone must keep clear, its web, its walls, its rim to thicken | The algorithm |
| Level grower | Walking a level's zones and building each brief | Which algorithm grows a zone |

**Growing**

| Concept | Owns | Never knows |
|---|---|---|
| Sampler (role) | The one question: "grow this zone's vegetation from this brief" | Any algorithm |
| Gibbs sampler (variant) | Birth and death moves under a fitted Gibbs process | The field sampler, the level, the CLI |
| Field sampler (variant) | Drawing a cellular mask, then covering it with decorations | The Gibbs sampler, the level, the CLI |
| Cellular field | The Worley `F2 - F1` field and its coverage per edge bin | Decorations |
| Zone growth (value) | The objects placed in one zone and the tiles they block | How they were chosen |

**Placement rules**

| Concept | Owns | Never knows |
|---|---|---|
| Zone canvas | The zone's occupancy under the hard rules: legal placement, removal, connectivity | Why a placement is proposed |
| Zone mix | The zone's expected category counts, and the draws of a category and an identity | Occupancy |
| Zone stream | The zone's own random stream, mixed from the seed and the zone id | Everything else |

**Corpus model**: one concept, the fitted model (value). It is shared as a read-only
reference.

**Finishing**: the border seal, the pocket check and the published result. These are
unchanged and out of scope.

**Assembly**

| Concept | Owns | Never knows |
|---|---|---|
| Sampler table | The name-to-sampler map the user chooses from | How a sampler works |

The zone brief and the zone growth are shared value types between Planting brief, Growing
and Finishing. The corpus model is a read-only reference.

## 3. Invariants

- **No blocking cell on the web or a forbidden tile.** The zone canvas owns this. It refuses
  the placement. Both variants uphold it by placing only through the canvas.
- **No open ground walled off inside a zone.** The zone canvas owns this, on every addition
  and every removal. It refuses the move.
- **No walled-off pocket on the finished level.** Finishing owns this. It raises.
- **Same seed, same map.** The zone stream owns this. Every draw a variant makes comes from
  it, in a fixed order.

## 4. Forces and patterns

Forces:

- F1. The growing algorithm varies. There are two today, and the user is still experimenting.
- F2. The hard rules must not vary with the algorithm, because every map must stay playable.
- F3. Tests run the level grower with either algorithm.
- F4. The user chooses the algorithm at run time.
- F5. The Gibbs output must stay byte-identical, so its draw order cannot change.

Between parts: a sequence of stages, as today. The step runs Planting brief, Growing and
Finishing in order, and Assembly configures it.

Inside parts:

- Sampler: **strategy** (F1, F3). A protocol with one method, `sample(zone, model, seed,
  brief) -> growth`. Each variant is a class with no fields that implements it (claim 5). The
  level grower and the step take the role as a required parameter, with no default.
- Zone canvas and zone mix: **composition** (F2). Each variant's per-zone run holds a canvas
  and a mix as fields. No variant is a kind of canvas.
- Sampler table: **name table at the entry point** (F4).
- Cellular field, zone brief, zone growth, zone stream: plain functions and values. Nothing
  varies there.

Claims: 1, 2, 3 and 5 are re-derived from F1, F3 and F4. Claim 4 is re-derived from F2.

The role is named `Sampler` because the user uses that word, and both algorithms draw a
random vegetation configuration fitted to the corpus. It names what the consumer asks, not
one variant (A2).

SOLID check:

- **Single responsibility.** The canvas used to own the draws too. That is now the zone mix.
  Every Owns reads without "and" except the canvas's list of hard rules, which is one
  responsibility: occupancy under the rules.
- **Open/closed.** A third sampler is one package and one table line.
- **Liskov substitution.** Each variant is a kind of Sampler only. Neither extends the canvas
  or the other variant.
- **Interface segregation.** Sampler declares the one method the level grower calls.
- **Dependency inversion.** The level grower and the step never know Gibbs or field. Only the
  sampler table does.

Open lookups:

- Which callers name a variant today (resolved in section 5).
- Whether the canvas's state is written from outside it (resolved in section 5).

## 5. Mapping onto the existing system

Revision log: none. The mapping changed no part or concept.

| Item | Verdict | Where, and the mismatch |
|---|---|---|
| Zone brief | Exists | `canvas.py:25` `SampleOptions`. It moves to the role's module. |
| Level grower | Reshape | `grow.py:17,61` imports `sample_zone` and uses it as the default sampler. That is rule 1.10's default variant. |
| Sampler role | Reshape | `grow.py:19` is a `Callable` alias in the consumer's module, which also imports Gibbs. It becomes a protocol in `vegetation/sampler.py`, which imports no variant. |
| Gibbs sampler | Reshape | `sample.py:113` `_ZoneSampler(ZoneCanvas)` is a kind of canvas. It moves to `vegetation/gibbs/`, holds a canvas, and exposes `GibbsSampler`. |
| Field sampler | Reshape | `field_fill.py:53` `_FieldFiller(ZoneCanvas)` is the same. It moves to `vegetation/field/` as `FieldSampler`. |
| Cellular field | Exists | `field.py`. It moves to `vegetation/field/`. |
| Zone growth | Exists | `canvas.py:21` `ZoneGrowth`. It moves to the role's module. |
| Zone canvas | Reshape | `sample.py:268-281` `_remove` writes the canvas's `blkcnt` and `nblocked` directly, and `sample.py:139` `frees_connected` is a connectivity rule living in Gibbs. Both move into the canvas as `remove`. The canvas owns the connectivity invariant, so it offers the removal. |
| Zone mix | New | `canvas.py:78-83,106-113` hold the category mix and the draws inside the canvas. They move to their own class in `vegetation/mix.py`. |
| Zone stream | Exists | `canvas.py:32` `zone_rng`. |
| Corpus model | Exists | `model.py` `VegModel`. |
| Vegetation step | Reshape | `step.py:119` `_sampler` is an override hook naming Gibbs. The step takes `sampler: Sampler` in its constructor instead. |
| Field step | Waste | `field_step.py:12` `FieldVegetationStep(VegetationStep)` is a variant written as a subclass of the working step. It is deleted. |
| Sampler table | Reshape | `cli/steps.py:30` `VEGETATION_STEPS` maps names to step classes. It becomes `SAMPLERS`, mapping names to sampler instances. |

Other callers:

- `cli/veg_experiment.py:8` is an entry point, so it may name Gibbs. It calls `GibbsSampler`.
- `core/planning/web.py:73` names `sample_zone` in a docstring. The docstring is updated.
- `core/steps/gated_step_test.py:25`, `gameplay_step_test.py:20` and
  `steps_write_map_test.py:66` build `VegetationStep`. They pass `GibbsSampler()`.

What the existing system has that the design lacks: `border_plan.py` and `result.py` belong
to Finishing, which is out of scope. Nothing is missing.

Claims against the code: the code follows none of claims 1 to 5 today. The design follows all
five.

## 6. Slices

1. **One step, the sampler chosen by the CLI.**
   - Changes: the Sampler protocol in `sampler.py`, `GibbsSampler` and `FieldSampler` as thin
     classes over today's functions, `VegetationStep(sampler=...)`, the `SAMPLERS` table, and
     `FieldVegetationStep` deleted.
   - Done when both `--vegetation` values run, `make golden` passes, the six baseline hashes
     match, and `make check` passes.
2. **Variants in their own packages, the canvas composed.**
   - Changes: `gibbs/` and `field/`, the canvas held as a field, `remove` moved into the
     canvas, and the zone mix split out.
   - Done when the same checks pass and no class under `vegetation/` extends `ZoneCanvas`.
3. **Docs.** `core/steps/AGENTS.md`, `vegetation/AGENTS.md` and the CLI help name the new
   shape. Done when a grep for `FieldVegetationStep`, `VEGETATION_STEPS`, `sample_zone`,
   `fill_zone` and `field_fill` finds no stale hit.

## 7. Assumptions

1. **Assumption**: the golden hashes and the six recorded hashes are today's output.
   - **Decided**: they are the refactor's oracle.
   - **Basis**: `make golden` passed before any edit. The six hashes were recorded from
     today's tree: `gibbs_s1_48 6cada8db`, `gibbs_s3_72_sub a837fa18`,
     `gibbs_s7_72 c473ad02`, `field_s1_48 62781f76`, `field_s3_72_sub 7901d9ec`,
     `field_s7_72 73b58c0c`.
   - **If wrong**: the section 6 done-whens.
2. **Assumption**: the role is named `Sampler`.
   - **Decided**: `Sampler.sample`.
   - **Basis**: the user's word. Both variants draw a random configuration.
   - **If wrong**: rename the role in section 2 and its module.
3. **Assumption**: the variants need no per-run configuration.
   - **Decided**: they are classes with no fields, and the tuning constants stay module
     constants.
   - **Basis**: no flag or test varies them today.
   - **If wrong**: the constants become constructor fields of the variant.
4. **Assumption**: the corpus model stays one shared value, although some fields serve only
   one variant (`sigma`, `T` for Gibbs, `blk_cells` for field).
   - **Decided**: `VegModel` is unchanged.
   - **Basis**: each field is a fact about the corpus, not about an algorithm.
   - **If wrong**: split the model per variant, in section 2 Corpus model.
5. **Assumption**: the per-zone return value keeps the protected web as its third element.
   - **Decided**: `ZoneGrowth` is unchanged. The level grower ignores the web, and the tests
     read it.
   - **Basis**: `sample_test.py:55`, `field_fill_test.py:29`.
   - **If wrong**: `ZoneGrowth` becomes a dataclass without it.
