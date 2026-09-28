"""Locate the local VCMI user-data directory (Data/, Maps/, Mods/) and its config/ tree from
the environment the caller hands in.

Priority: the VCMI_HOME variable, then the platform's standard VCMI locations (first existing
wins). No candidate existing is an error that names VCMI_HOME.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VcmiInstall:
    home: Path
    data_dir: Path
    config_dirs: tuple[Path, ...]


class InstallNotFoundError(RuntimeError):
    pass


def _wsl_windows_home(env: Mapping[str, str]) -> Path | None:
    """Return the Windows user home via /mnt/c/Users when running inside WSL, else None."""
    try:
        if "microsoft" not in Path("/proc/version").read_text().lower():
            return None
    except OSError:
        return None
    mnt = Path("/mnt/c/Users")
    if not mnt.is_dir():
        return None
    me = env.get("USER") or env.get("LOGNAME") or ""
    for name in ([me] if me else []) + sorted(p.name for p in mnt.iterdir()):
        candidate = mnt / name
        if candidate.is_dir() and name not in ("Public", "Default", "All Users"):
            return candidate
    return None


def _user_home(env: Mapping[str, str], platform: str) -> Path | None:
    home = env.get("USERPROFILE") if platform == "win32" else env.get("HOME")
    return Path(home) if home else None


def _home_candidates(env: Mapping[str, str], platform: str) -> list[Path]:
    home = _user_home(env, platform)
    if home is None:
        return []
    if platform == "win32":
        return [home / "Documents" / "My Games" / "vcmi"]
    if platform == "darwin":
        return [home / "Library" / "Application Support" / "vcmi"]
    xdg = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
    cands = [home / ".var" / "app" / "eu.vcmi.VCMI" / "data" / "vcmi", xdg / "vcmi"]
    win_home = _wsl_windows_home(env)
    if win_home:
        cands.append(win_home / "Documents" / "My Games" / "vcmi")
    return cands


def _config_dirs(env: Mapping[str, str], platform: str) -> tuple[Path, ...]:
    """Directories that contain VCMI's core config/ tree (config/objects, config/creatures, ...).

    On a flatpak install this is the read-only share directory; on Windows / WSL it lives
    under AppData/Roaming/VCMI. Only existing candidates are kept.
    """
    candidates = [Path("/var/lib/flatpak/app/eu.vcmi.VCMI/current/active/files/share/vcmi/config")]
    home = _user_home(env, platform)
    if platform == "win32" and home is not None:
        candidates.append(home / "AppData" / "Roaming" / "VCMI" / "config")
    win_home = _wsl_windows_home(env)
    if win_home:
        candidates.append(win_home / "AppData" / "Roaming" / "VCMI" / "config")
    return tuple(c for c in candidates if c.is_dir())


def _expand(raw: str, env: Mapping[str, str], platform: str) -> Path:
    home = _user_home(env, platform)
    if home is not None and (raw == "~" or raw.startswith("~/")):
        return home / raw[2:]
    return Path(raw)


def find_install(env: Mapping[str, str], platform: str) -> VcmiInstall:
    raw = env.get("VCMI_HOME")
    cands = [_expand(raw, env, platform)] if raw else _home_candidates(env, platform)
    for home in cands:
        if home.is_dir():
            return VcmiInstall(home, home / "Data", _config_dirs(env, platform))
    looked = ", ".join(str(c) for c in cands) or "no candidate"
    raise InstallNotFoundError(
        f"no VCMI install found (looked in: {looked}); set VCMI_HOME to the VCMI data directory"
    )
