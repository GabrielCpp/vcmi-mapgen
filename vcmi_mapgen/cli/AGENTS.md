# cli/: the composition root

Every command a person runs starts here. `python -m vcmi_mapgen.cli <subcommand>` parses the
arguments in `__main__.py` and calls one module per subcommand.

## Map

- `__main__.py`: argument parsing and the subcommand table.
- `corpus_match.py`: the `corpus-match` subcommand. It generates maps from `build_steps` and prints the corpus comparison.
- `extract_vmap.py`: the `extract-vmap` subcommand. It regenerates `maps_vmap/` from the `.h3m` corpus.
- `generate.py`: the `generate` subcommand: pipeline run, overlays and renderers.
- `steps.py`: `build_steps`, the one step list, and the `--stop-after` names.
