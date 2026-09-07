# VCMI map-generator — repository root

A **learned procedural map generator** for VCMI / Heroes 3 maps: a corpus-fitted
marked-point-process pipeline synthesizes terrain, zones, gameplay objects, vegetation,
loot and repairs into a playable map (`cli.py generate`). Corpus statistics (`data/`,
`maps_vmap/`) are learned once from 159 real `.h3m` maps via `extract_vmap.py` and read
back by the generator's individual steps (mine/dwelling densities, vegetation
point-process parameters, macro-terrain style) — there is no separate rebuild/replay
engine; the corpus only ever informs *statistics*, never map content directly.

Load `vcmi-mapgen-maps` for the domain details (formats, segmentation, rendering).
Load `vcmi-mapgen-pipeline` before adding/changing a pipeline step or a `cli.py`
subcommand (the step contract, `MapState`, `ProviderRegistry`).

## Tooling — this is a `uv` Python project

- Run **everything** through uv as a module: `uv run python -m vcmi_mapgen.<module> [...]`.
  Dependencies (`pyproject.toml`): Pillow + numpy; everything else is stdlib. Never
  `pip install`; never assume a system interpreter — `uv run` resolves the env.
- Determinism: replay is integer-only; the terrain generator is seeded. Don't introduce
  `random`/time without a seed.

## Where things are

- **`vcmi_mapgen/`** — the package (run modules with `python -m vcmi_mapgen.<name>`):
  - `cli.py` — the CLI (`generate` / `render-ontology`), a thin layer over `pipeline.py`.
  - `pipeline.py` — `MapState` (the narrow, render-only view of a finished map),
    the Gameplay/Vegetation/Pickup/Repair collaboration workspaces, the `ProviderRegistry`
    (typed, memoized cross-step values), and the `PipelineStep`/`Pipeline` contract every
    step is built from. See `vcmi-mapgen-pipeline` for the contract itself and
    `steps/AGENTS.md` for what a step must do.
  - `steps/` — one subpackage per step: `terrain_gen/segment/gate/gameplay/vegetation/
    pickup/repair`.
  - `terrain_segment.py` — same-terrain flood-fill segmentation + interior-depth features.
  - `kit/objects.py`, `ontology.py` — corpus loader, object identity, purpose.
  - `kit/vmap/{reader,writer}.py` — the full `.vmap` reader/writer.
  - `renderers/sprites.py` — editor-quality 32px H3 sprite rendering (decodes DEF fmt
    0/1/2/3); `renderers/png.py` — schematic PNGs; `renderers/vmap.py` — playable `.vmap`
    export (`VmapRenderer` builds the `VmapDocument` directly from a finished `MapState`);
    `renderers/overlays/` — debug overlay layers (zone/blocking/pocket/...), only
    `generate` selects these from the CLI; `renderers/ontology_render.py` — the
    `render-ontology` catalog dump (a documentation tool, not part of the pipeline).
  - `steps/terrain_gen/markov.py` — the terrain generator (Markov chain learned from
    the corpus), consumed by `steps/terrain_gen/macro_topo.py`.
  - `h3m.py`, `vcmi_ids.py`, `extract_vmap.py` — `.h3m` → `.vmap` corpus-extraction pipeline.
  - `renderers/sprites_test.py` — rendering-engine reliability tests.
- **`maps/`** — the `.h3m` corpus (159 maps), the source data.
- **`maps_vmap/`** — one real `.vmap` per corpus map (the engine's input; regenerable from
  `maps/` via `extract_vmap.py`).
- **`data/`** — corpus-derived priors (`objlib.json`, `pp/*.json` — macro/gameplay/vegetation
  statistics) and static VCMI-derived reference tables (`objclass_names.json` — the raw
  MapObjectID enum, feeding `ontology.py --regen`; `vmap_header_template.json`). Static
  VCMI/corpus-derived JSON lives here, never loose beside the `.py` sources — if you add a
  reference table, it goes in `data/`.
- **`out/`** — transient outputs (templates, features, renders); **gitignored**.
- **`vcmi-h3m-format-reference/`** — verbatim VCMI C++ sources documenting the `.h3m` format
  (see `docs/vcmi-h3m-format-reference.md`).

## How to run

```bash
uv run python -m vcmi_mapgen.cli generate --seed 3 --size 72    # procedural generator
uv run python -m vcmi_mapgen.extract_vmap                      # regenerate maps_vmap/ from maps/
uv run pytest                                                  # rendering-engine reliability tests
```

Editor-quality rendering reads the H3 sprite LOD files from a local VCMI install
(`~/.var/app/eu.vcmi.VCMI/data/vcmi/Data`); the rendering tests skip when those are absent.

## Rules

- **`ontology.py` is the SINGLE SOURCE OF TRUTH for objects, from tile placement through map
  rendering.** Object identity, footprint mask, terrain coupling and decoration category for the
  *generation* pipeline come from `ontology.py` — the hardcoded `TAXONOMY` + `LEAF_META` literals,
  re-derived from the authoritative editor table `objects.txt` via `python -m vcmi_mapgen.ontology
  --regen`. Use its accessors (`identity_of`, `mask_of`, `is_blocking`, `terrains_of`, `decor_pool`,
  `veg_categories`, `category_of`, `decode_identity`, `category_terrain_matrix`). When something the
  pipeline needs is missing, **extend the ontology** (parse it from `objects.txt` and regenerate) —
  do NOT reach into the corpus (`data/objlib.json` / `obj_resolve._OBJLIB`, faithful maps, or a
  `veg_data` corpus scan) for object identity/mask/category. The corpus may still inform spatial
  *statistics* (density/openness/frequency weights), never identity. `veg_data`'s category functions
  are thin ontology adapters.
- **Every pipeline step must write onto `MapState`** — there are no ctx-only steps. Anything
  else a step produces for a later step goes through the `ProviderRegistry` as a typed
  dataclass, never a raw string-keyed dict entry. See `steps/AGENTS.md` for the full
  contract.
- Generated artifacts live in `out/` (gitignored). Do **NOT** copy them into the VCMI
  `Maps/` folder.
- Treat `CLAUDE.md` and `.claude/` as generated adapter outputs — edit the canonical skill
  sources and re-run `make agent-install`, never hand-edit them.

---

# CLI & Makefile Command Timeouts

**Every command an agent can run must be bounded by a wall-clock timeout.** A
command without a timeout can block forever — a dev server that never returns, a
test runner waiting on a missing service, a `docker compose up` with no
healthcheck, a prompt for stdin. An autonomous agent has no human to hit
`Ctrl-C`, so an unbounded command stalls the whole run until an outer timeout
(if any) kills it minutes or hours later.

This applies in two places: **Makefile/script recipes you author** and **ad-hoc
shell commands an agent runs directly**.

---

## Rule 1 — Makefile & script recipes wrap blocking commands in `timeout`

Any recipe whose command can block — tests, lint, build, codegen, dev servers,
`docker compose`, DB waits, network calls — wraps the command in
`timeout <seconds> <command>`. Trivially-fast, non-blocking commands (`echo`,
`rm`, `mkdir`, `cp`, `gofmt -l`) do not need one.

```makefile
# ✅ blocking commands are bounded
test:
	@echo "Running tests..."
	timeout 300 go test ./...

lint:
	@echo "Running linters..."
	timeout 60 go vet ./...

generate:
	@echo "Generating code from OpenAPI spec..."
	timeout 90 go run ./cmd/codegen ...

dev:
	@echo "Starting dev server..."
	timeout 120 npm run dev
```

```makefile
# ❌ unbounded — an agent calling `make test` hangs if a test deadlocks
test:
	go test ./...
```

### Standard ceilings

Pick the smallest ceiling that comfortably exceeds the normal run. The timeout is
a safety net against *hangs*, not a performance budget — leave generous headroom
so a slow-but-healthy run never trips it.

| Recipe kind | Typical ceiling |
|---|---|
| Lint / typecheck / vet | 30–60s |
| Codegen (OpenAPI, sqlc, mocks) | 60–120s |
| Unit tests | 120–300s |
| Build | 120–300s |
| Integration tests (Docker/DB) | 300–600s |
| Dev server / watch (foreground) | 60–120s |

### Recipes that wait on a service

A bare `sleep` to "wait for the database" is itself an unbounded gamble — the
service may never come up. Prefer a bounded readiness poll, and bound the
`docker compose up` and the test run too:

```makefile
# ✅ bounded bring-up, bounded wait-loop, bounded test run, guaranteed teardown
test-integration:
	timeout 120 docker compose -f docker-compose.dev.yml up -d mysql-test
	timeout 60 sh -c 'until docker compose exec -T mysql-test mysqladmin ping --silent; do sleep 1; done'
	INTEGRATION_TEST=1 timeout 600 go test -tags=integration ./internal/... ; status=$$? ; \
		docker compose -f docker-compose.dev.yml down ; exit $$status
```

Note the teardown runs even when the test run times out (the `; status=$$? ; ...
; exit $$status` pattern), so a hang never leaks containers.

### Recipes that compose other recipes

When a recipe just calls sub-`make`s (e.g. a root `test` that runs `cd api &&
make test` then `cd web && make test`), the timeout belongs on the **leaf**
recipes, not the aggregator. Don't double-wrap — a `timeout` around a `make`
that already wraps its commands only muddies which limit fired.

---

## Rule 2 — Ad-hoc shell commands an agent runs get a timeout too

When you (the agent) run a command directly rather than through a recipe, apply
the same discipline. The harness's own tool timeout is a last resort, not a
plan: wrap commands that can block so a hang fails fast and visibly.

- **Servers, watchers, REPLs, `tail -f`, `logs -f`** — these never return by
  design. Either run them with a `timeout` (to capture N seconds of output) or
  start them in the background and poll, rather than blocking the foreground.
- **Test / build / codegen invoked directly** — prefer the Makefile recipe (it
  already carries the ceiling). If you must run the raw command, add `timeout`.
- **Network calls** (`curl`, `gh`, package installs) — bound them; a hung TLS
  handshake or auth prompt otherwise blocks indefinitely.

```bash
# ✅ bound a direct test run
timeout 300 go test ./internal/foo/...

# ✅ capture 10s of server logs instead of blocking forever
timeout 10 npm run dev

# ❌ blocks the agent until an outer limit kills it
go test ./...        # may deadlock
npm run dev          # never returns
```

---

## Behaviour & exit codes

- `timeout` exits **124** when the command is killed for exceeding the limit.
  Treat 124 as a hang/too-slow signal distinct from the command's own failure.
- For commands that ignore `SIGTERM`, use `timeout --kill-after=<dur> <limit>`
  so a `SIGKILL` follows if the process doesn't exit promptly.
- `timeout` is part of GNU coreutils; it is present on Linux and in CI/Docker
  images. On a bare macOS dev box it may need `coreutils` (`gtimeout`) — the
  agent and CI run on Linux, so author recipes for `timeout`.

## Checklist before adding or editing a recipe

- [ ] Does this command ever block, wait, serve, or watch? → wrap in `timeout`.
- [ ] Is the ceiling generous vs. a healthy run but still bounded? 
- [ ] Does any service it starts get torn down even on timeout?
- [ ] Are pure-filesystem / `echo` steps left unwrapped (no needless timeout)?
