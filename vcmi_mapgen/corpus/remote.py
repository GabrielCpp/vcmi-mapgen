"""Load and save the remote distance per map size in ``data/pp/remote.json``."""

from pathlib import Path

from vcmi_mapgen.core.priors.remote import RemotePriors
from vcmi_mapgen.corpus import cache
from vcmi_mapgen.vcmi.formats import json_value as jv

REMOTE_FILE = "remote.json"
REMOTE_VERSION = 1
REMOTE_SOURCE = "vcmi_mapgen.corpus.mine.remote.mine_remote"


def load_remote(pp_dir: Path) -> RemotePriors:
    """The remote distances in ``remote.json``, or the built-in ones when the file is
    absent."""
    if not (pp_dir / REMOTE_FILE).exists():
        return RemotePriors()
    st = cache.read(pp_dir / REMOTE_FILE, version=REMOTE_VERSION)
    return RemotePriors(
        {int(size): jv.as_int(k) for size, k in jv.as_object(st.get("reach")).items()}
    )


def save_remote(pp_dir: Path, st: RemotePriors) -> None:
    cache.write(
        pp_dir / REMOTE_FILE,
        REMOTE_SOURCE,
        {"_version": REMOTE_VERSION, "reach": {str(s): k for s, k in sorted(st.reach.items())}},
    )
