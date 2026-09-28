---
name: vcmi-mapgen-target-architecture
description: "Settle a repository's target architecture before refactoring it, then turn it into a migration plan a workflow can execute. Produces two files: docs/architecture/target.md, the human contract (target tree, core models and the facts they own, sources of truth, allowed dependency edges, behaviour oracle), and docs/architecture/plan.json, the machine contract (a fate for every source file and ordered slices with touches, depends_on and done_when). Ships a validator that checks every file has a fate and that slices able to run in parallel touch disjoint files. Nothing moves until the operator sets status to approved. Load before a repo-wide refactor or restructuring, when asked what the architecture should be, or before running a refactor workflow."
metadata:
  generated_by: farrier
  source: library/skills/target-architecture/SKILL.md
  resolve: "farrier source .claude/skills/vcmi-mapgen-target-architecture/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [architecture, refactoring, planning]
---

# Target architecture

A refactor done file by file drifts. Each change looks right locally, and the fifth one
undoes the second because nobody wrote down where things end up. An agent asked to "clean
up" without a target cleans toward its own taste, which differs per session. This skill
fixes the destination first, gets the operator to sign it, and then cuts the route into
slices small enough that each one ends green.

Load `codebase-map`, `dead-code` and `code-structure` with this skill. The inventory uses
all three.

## Outputs

| File | Reader | Holds |
|------|--------|-------|
| `docs/architecture/target.md` | the operator, every later session | the decisions and the reason for each |
| `docs/architecture/plan.json` | the refactor workflow, `scripts/check_plan.py` | fates and slices |
| the import contract | the repo's check suite | allowed dependency edges, enforced |

Paths under a hidden directory such as `.claude/` never count as sources. Override the
plan path, the source globs and excluded paths in `.agent-checks.toml`:

```toml
[target-architecture]
plan = "docs/architecture/plan.json"
sources = ["*.py"]
exclude = ["docs/*", "scripts/*"]
```

## Procedure

Work in this order. Each phase writes its section of `target.md` before the next begins.

### 1. Inventory the present

- **Map.** Read every `## Map` section. Where a directory has none, write one line per
  file from reading it. A file whose line needs "and" holds two concerns.
- **Dead code.** Run the `dead-code` procedure to its classify step. Dead modules get the
  fate `delete` and go in the first slice. Do not design around code nobody runs.
- **Rule hits.** Walk the `code-structure` trigger table over the tree. Record each hit as
  `path:line rule-number one-line`. The operator's own complaints go in verbatim, and
  each one gets a rule number or a new rule.
- **Import graph.** Record which top-level directories import which. Every cycle and
  every import from a shared layer into a feature layer is a finding.

The inventory is evidence. It goes in an appendix of `target.md`, not in the decisions.

### 2. Decide the target

Write each of these as a short section. Each decision carries the finding that forced it.

1. **Core models and the facts they own.** Name each core model and list the facts that
   define it. Everything else computed from it is analysis, and analysis lives beside
   its producer, not on the model (rule 1.5). Name one model per real-world thing (1.6).
2. **Sources of truth.** For each kind of domain fact, name the one module that answers
   it: object identity, constants of the file format, configuration. Every other module
   queries that owner and never restates the fact (2.7, 2.8). An unused accessor on an
   owner is a sign some caller hardcodes its answer.
3. **The target tree.** Every directory gets one kind line: "one subpackage per pipeline
   step", "pure geometry on grids", "readers and writers of external formats". A
   directory holds one kind of thing (2.9). Draw the tree to the depth of directories and
   the files whose placement is a decision.
4. **Allowed dependency edges.** A layer list or a table of permitted imports. Write it
   as the stack's contract tool config, so the check suite enforces it:
   - Python: `import-linter` contracts in `pyproject.toml` (`layers`, `forbidden`,
     `independence`).
   - TypeScript: `dependency-cruiser` rules.
   - Go: `go-arch-lint`, or `internal/` packages where visibility is enough.
5. **Invariants.** The few sentences a reviewer checks every diff against, such as "the
   map model holds grid facts only". Each one names the rule it comes from.
6. **The behaviour oracle.** How a slice proves it changed structure and not behaviour.
   For a deterministic program, record golden outputs on fixed inputs before any slice
   runs, and compare byte for byte after each one. Otherwise use the test suite plus the
   characterisation tests you add in slice zero. A refactor slice that changes the oracle
   is a failed slice.

### 3. Assign every file a fate

Every tracked source file gets exactly one fate in `plan.json`:

| Fate | Meaning | Needs |
|------|---------|-------|
| `keep` | stays where it is, maybe edited | nothing |
| `move` | same content, new path | `to`, `slice` |
| `split` | its concerns go to several files | `to` (list), `slice` |
| `merge` | joins another file | `to`, `slice` |
| `delete` | dead, or replaced by an owner's query | `slice` |

A file that is both moved and rewritten gets `move` here, and the rewrite is its own
slice.

### 4. Cut the route into slices

A slice is one reviewable change that leaves the repo green. Rules:

- **Slice zero records the oracle.** Golden outputs, characterisation tests, and the
  contract tool installed with the current violations listed as ignores.
- **Slice one deletes dead code.** Everything downstream is smaller for it.
- **One concern per slice.** "Move reachability queries onto the map model" is a slice.
  "Clean up kit/" is not.
- **Moves before rewrites.** Moving a file and rewriting it in one diff hides the rewrite
  inside a rename.
- **Every slice removes contract ignores or adds none.** The last slice removes the last
  ignore.
- **`touches` is exact.** List every file or directory glob the slice may edit, including
  tests and docs. The workflow refuses edits outside it.
- **Parallel means disjoint.** Two slices with no dependency path between them must touch
  disjoint paths. The validator enforces it.
- **`done_when` is checkable.** A command that passes, a grep that returns nothing, an
  oracle that matches. Never "code is cleaner".
- **`rules` cites** the `code-structure` rule numbers or invariants the slice serves.

### 5. Validate and stop for approval

```bash
python3 <skill>/scripts/check_plan.py            # every file has a fate, slices are sound
python3 <skill>/scripts/check_plan.py --waves    # print the parallel execution waves
```

Write `plan.json` with `"status": "draft"`. Present `target.md` to the operator with the
waves, and stop. Only the operator sets `"status": "approved"`. A workflow refuses to run
a draft. A change of target after approval is a new draft, and slices already merged stay
merged.

## `plan.json`

```json
{
  "status": "draft",
  "oracle": "make golden && git diff --exit-code tests/golden",
  "check": "make check",
  "fates": {
    "pkg/kit/reachability.py": {"fate": "delete", "slice": "s01-dead"},
    "pkg/steps/placement.py": {"fate": "move", "to": "pkg/placement/cells.py", "slice": "s02-placement"},
    "pkg/models/map_state.py": {"fate": "keep"}
  },
  "slices": [
    {
      "id": "s00-oracle",
      "goal": "Record golden outputs for seeds 1-5 and install the import contract with current violations ignored",
      "touches": ["tests/golden/*", "pyproject.toml", "Makefile"],
      "depends_on": [],
      "done_when": ["make golden && git diff --exit-code tests/golden", "uv run lint-imports"],
      "rules": []
    },
    {
      "id": "s01-dead",
      "goal": "Delete modules no entry point reaches, with their tests and doc mentions",
      "touches": ["pkg/kit/reachability.py", "pkg/steps/portal/geometry_test.py", "AGENTS.md"],
      "depends_on": ["s00-oracle"],
      "done_when": ["python3 <dead-code>/scripts/py_unreachable.py --check"],
      "rules": ["2.10"]
    }
  ]
}
```

`oracle` and `check` run after every slice. A slice's own `done_when` runs after them.

## Rules

- **Settle before moving.** No code moves under this skill until the plan is approved.
  A refactor that starts before the target is written ends where the last session's
  taste left it.
- **The target is small.** One screen for the tree, one for the models and owners, one
  for the edges. A target that needs ten pages has not been decided yet.
- **Name what stays wrong.** Debt left out of scope is listed in `target.md` with the
  reason. Silence reads as approval to the next session.
- **The contract outlives the refactor.** The import contract and the invariants stay in
  the check suite after the last slice merges. They keep the next change on the target.
