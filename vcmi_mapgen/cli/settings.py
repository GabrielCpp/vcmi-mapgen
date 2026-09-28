from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall, find_install


def project_root() -> Path:
    """The checkout directory that holds the ``vcmi_mapgen`` package."""
    return Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    """The environment facts one run reads: the process environment, the platform, and the
    checkout root every cache, corpus and output directory hangs off."""

    env: Mapping[str, str]
    platform: str
    root: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str], platform: str) -> Settings:
        return cls(dict(environ), platform, project_root())

    @property
    def pp_dir(self) -> Path:
        """The mined corpus statistics, ``data/pp/``."""
        return self.root / "data" / "pp"

    @property
    def maps_dir(self) -> Path:
        """The corpus maps as ``.vmap``, ``maps_vmap/``."""
        return self.root / "maps_vmap"

    @property
    def h3m_dir(self) -> Path:
        """The corpus maps as ``.h3m``, ``maps/``."""
        return self.root / "maps"

    @property
    def out_dir(self) -> Path:
        """Every rendered or generated file, ``out/``."""
        return self.root / "out"

    def install(self) -> VcmiInstall:
        return find_install(self.env, self.platform)


def load_settings() -> Settings:
    return Settings.from_env(os.environ, sys.platform)


def open_install(settings: Settings) -> VcmiInstall:
    try:
        return settings.install()
    except InstallNotFoundError as e:
        raise SystemExit(str(e)) from None
