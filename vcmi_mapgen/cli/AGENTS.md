# cli/: the composition root

Every command a person runs starts here. `python -m vcmi_mapgen.cli <subcommand>` parses the
arguments in `__main__.py` and calls one module per subcommand.
