"""project_root() for the vcmi-mapgen repository root."""

import pathlib


def project_root() -> pathlib.Path:
    """The vcmi-mapgen project root directory (parent of the vcmi_mapgen package)."""
    return pathlib.Path(__file__).parent.parent.parent
