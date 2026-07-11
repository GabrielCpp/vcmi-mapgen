"""System-aware discovery of the local VCMI installation.

Several parts of the pipeline read files from a real VCMI install: the renderer needs
the H3 sprite LOD archives (`Data/`), the .vmap writer needs an existing map to lift a
header template from (`Maps/`), `vcmi_ids` needs VCMI's own object config
(`config/` + `Mods/`), and `--install` copies generated maps back into `Maps/`.

Those live somewhere different on every platform (and under Flatpak, somewhere different
again), so no module may hardcode a path — ask here instead.

Every lookup can be overridden with an environment variable, which always wins:

    VCMI_HOME        user data dir: holds Data/, Maps/, Mods/, config/
    VCMI_DATA_DIR    dir holding H3sprite.lod & friends
    VCMI_MAPS_DIR    dir holding .h3m / .vmap maps
    VCMI_INSTALL     installed share dir: holds config/, Mods/
    VCMI_VMAP_TEMPLATE  a specific .vmap to lift the header template from

Nothing here raises on a missing install: the getters return the best candidate (so error
messages name a concrete path) and callers/tests check `os.path.isdir` themselves.
"""

import glob
import os
import sys

LOD_FILES = ["H3sprite.lod", "H3ab_spr.lod", "H3bitmap.lod", "H3ab_bmp.lod"]


def _first_dir(candidates, default=None):
    """First candidate that exists, else `default` (or the first candidate)."""
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return default if default is not None else (candidates[0] if candidates else "")


def _home_candidates():
    """User data dirs (Data/, Maps/, Mods/, config/), most-likely first."""
    x = os.path.expanduser
    if sys.platform == "darwin":
        return [x("~/Library/Application Support/vcmi")]
    if sys.platform.startswith("win"):
        return [x("~/Documents/My Games/vcmi")]
    # Linux / BSD: Flatpak, then XDG.
    xdg = os.environ.get("XDG_DATA_HOME") or x("~/.local/share")
    return [x("~/.var/app/eu.vcmi.VCMI/data/vcmi"), os.path.join(xdg, "vcmi")]


def _install_candidates():
    """Installed share dirs (config/, Mods/ shipped with VCMI itself)."""
    x = os.path.expanduser
    if sys.platform == "darwin":
        return [
            "/Applications/VCMI.app/Contents/Resources/Data",
            x("~/Applications/VCMI.app/Contents/Resources/Data"),
        ]
    if sys.platform.startswith("win"):
        return [
            r"C:\Program Files\VCMI",
            r"C:\Program Files (x86)\VCMI",
        ]
    return [
        "/var/lib/flatpak/app/eu.vcmi.VCMI/current/active/files/share/vcmi",
        x("~/.local/share/flatpak/app/eu.vcmi.VCMI/current/active/files/share/vcmi"),
        "/usr/share/vcmi",
        "/usr/local/share/vcmi",
    ]


def vcmi_home():
    """User data dir — Data/, Maps/, Mods/, config/ live under it."""
    env = os.environ.get("VCMI_HOME")
    if env:
        return os.path.expanduser(env)
    return _first_dir(_home_candidates())


def vcmi_install():
    """Dir of the VCMI installation itself (ships config/ and the base Mods/)."""
    env = os.environ.get("VCMI_INSTALL")
    if env:
        return os.path.expanduser(env)
    return _first_dir(_install_candidates())


def data_dir():
    """Dir holding the H3 sprite LOD archives."""
    env = os.environ.get("VCMI_DATA_DIR")
    if env:
        return os.path.expanduser(env)
    return _first_dir([os.path.join(vcmi_home(), "Data")])


def has_lod():
    """True when the H3 sprite archives are actually present (tests skip if not)."""
    d = data_dir()
    return os.path.isdir(d) and any(os.path.exists(os.path.join(d, f)) for f in LOD_FILES)


def maps_dir():
    """Dir holding VCMI's maps (.h3m / .vmap)."""
    env = os.environ.get("VCMI_MAPS_DIR")
    if env:
        return os.path.expanduser(env)
    return _first_dir([os.path.join(vcmi_home(), "Maps")])


def install_maps_dir(sub="pp-gen"):
    """Where `--install` drops generated maps so the editor lists them."""
    return os.path.join(maps_dir(), sub) if sub else maps_dir()


def config_bases():
    """Roots to scan for VCMI's object/creature/faction JSON (see `vcmi_ids`).

    Both the shipped config and any user mods are searched; the caller globs
    `{base}/{sub}/*.json` and `{base}/**/config/{sub}/*.json` under each.
    """
    inst, home = vcmi_install(), vcmi_home()
    bases = [
        os.path.join(inst, "config"),
        os.path.join(inst, "Mods"),
        os.path.join(home, "config"),
        os.path.join(home, "Mods"),
    ]
    return [b for b in bases if os.path.isdir(b)] or bases


def find_vmap_template():
    """An existing .vmap whose header we clone when writing a new map.

    VCMI writes random maps into `Maps/RandomMaps/`, so that's the usual source; any
    .vmap under Maps/ will do. Returns None when the install has none — callers should
    say so plainly rather than crash on an empty glob.
    """
    env = os.environ.get("VCMI_VMAP_TEMPLATE")
    if env:
        p = os.path.expanduser(env)
        return p if os.path.exists(p) else None
    m = maps_dir()
    hits = sorted(glob.glob(os.path.join(m, "RandomMaps", "*.vmap"))) or sorted(
        glob.glob(os.path.join(m, "**", "*.vmap"), recursive=True)
    )
    return hits[0] if hits else None


def vmap_template_or_die():
    """`find_vmap_template()`, but with an actionable error instead of an IndexError."""
    p = find_vmap_template()
    if not p:
        raise FileNotFoundError(
            f"No .vmap template found under {maps_dir()!r}. Save a random map from VCMI "
            f"(it lands in Maps/RandomMaps/), or point VCMI_VMAP_TEMPLATE at a .vmap."
        )
    return p


if __name__ == "__main__":
    print(f"platform      {sys.platform}")
    print(f"vcmi_home     {vcmi_home()}  exists={os.path.isdir(vcmi_home())}")
    print(f"vcmi_install  {vcmi_install()}  exists={os.path.isdir(vcmi_install())}")
    print(f"data_dir      {data_dir()}  lod={has_lod()}")
    print(f"maps_dir      {maps_dir()}  exists={os.path.isdir(maps_dir())}")
    print(f"install_maps  {install_maps_dir()}")
    print(f"config_bases  {config_bases()}")
    print(f"vmap_template {find_vmap_template()}")
