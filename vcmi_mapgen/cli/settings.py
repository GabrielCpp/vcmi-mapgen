from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall, find_install


@dataclass(frozen=True, slots=True)
class Settings:
    env: Mapping[str, str]
    platform: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str], platform: str) -> Settings:
        return cls(dict(environ), platform)

    def install(self) -> VcmiInstall:
        return find_install(self.env, self.platform)


def load_settings() -> Settings:
    return Settings.from_env(os.environ, sys.platform)


def open_install(settings: Settings) -> VcmiInstall:
    try:
        return settings.install()
    except InstallNotFoundError as e:
        raise SystemExit(str(e)) from None
