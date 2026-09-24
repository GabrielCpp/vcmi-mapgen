# Thin entrypoint — includes the generated agent launcher.
#
# All agent commands (agent-run / agent-native / agent-build / agent-install /
# agent-check / ...) come from the generated .agents/agents.mk. Run `make help`
# to list them. Add your own repo-specific (non-agent) targets below the include.
include .agents/agents.mk

.PHONY: check
check:
	uv run ruff check vcmi_mapgen
	uv run ruff format --check vcmi_mapgen
	uv run basedpyright
	uv run pytest -q
