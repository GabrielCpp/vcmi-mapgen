# Thin entrypoint — includes the generated agent launcher.
#
# All agent commands (agent-run / agent-native / agent-build / agent-install /
# agent-check / ...) come from the generated .agents/agents.mk. Run `make help`
# to list them. Add your own repo-specific (non-agent) targets below the include.
include .agents/agents.mk

.PHONY: check lint test sweep golden golden-update
check: lint test

lint:
	uv run ruff check vcmi_mapgen
	uv run ruff format --check vcmi_mapgen
	uv run basedpyright
	uv run lint-imports

test:
	uv run python -m pytest -q -n auto --dist loadfile

sweep:
	uv run python -m pytest -q -n auto -m slow

golden:
	uv run python -m pytest -q -n 2 -m golden vcmi_mapgen/golden_test.py

golden-update:
	GOLDEN_UPDATE=1 uv run python -m pytest -q -p no:xdist -m golden vcmi_mapgen/golden_test.py
