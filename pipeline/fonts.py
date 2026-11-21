"""Portable font lookup: Windows fonts when present, free equivalents on Linux (Muse) and macOS.

Roles map to ordered candidate file names; the first one found in assets/fonts (recursively) or any system
font folder wins. On Linux install e.g. `fonts-liberation fonts-dejavu-core` and put Oswald-Bold.ttf
(Google Fonts, OFL) in assets/fonts/ for the condensed role.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .common import ASSETS

ROLES: dict[str, list[str]] = {
    # bold sans for burned-in subtitles and review labels
    "sans_bold": ["arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf",
                  "Arial Bold.ttf"],
    # outro tagline / signature
    "serif_italic": ["georgiai.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf",
                     "NotoSerif-Italic.ttf", "Georgia Italic.ttf", "timesi.ttf"],
    "serif_bold": ["georgiab.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf", "NotoSerif-Bold.ttf",
                   "Georgia Bold.ttf", "timesbd.ttf"],
    # "PART N" on covers (matches the thumbnail's "EPISODE n")
    "condensed_bold": ["bahnschrift.ttf", "Oswald-Bold.ttf", "Oswald[wght].ttf", "Oswald-VariableFont_wght.ttf",
                       "BebasNeue-Regular.ttf", "LiberationSansNarrow-Bold.ttf", "DejaVuSansCondensed-Bold.ttf",
                       "impact.ttf"],
    "impact": ["impact.ttf", "Anton-Regular.ttf", "Oswald-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "serif_regular": ["georgia.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "NotoSerif-Regular.ttf",
                      "Georgia.ttf", "times.ttf"],
}
# variable fonts: which named instance to use
VARIATIONS = {"bahnschrift.ttf": "Bold Condensed", "Oswald[wght].ttf": "Bold", "Oswald-VariableFont_wght.ttf": "Bold"}


def _dirs() -> list[Path]:
    home = Path.home()
    return [ASSETS / "fonts", Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
            home / "AppData/Local/Microsoft/Windows/Fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            home / ".fonts", home / ".local/share/fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
            home / "Library/Fonts"]


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """lower-case file name → path, first folder wins (assets/fonts before system fonts)."""
    idx: dict[str, str] = {}
    for d in _dirs():
        if not d.is_dir():
            continue
        try:
            for p in d.rglob("*"):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    idx.setdefault(p.name.lower(), str(p))
        except OSError:
            continue
    return idx


def path(role: str) -> str | None:
    idx = _index()
    for name in ROLES[role]:
        p = idx.get(name.lower())
        if p:
            return p
    return None


def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    p = path(role)
    if not p:
        return ImageFont.load_default(size)
    f = ImageFont.truetype(p, size)
    var = VARIATIONS.get(Path(p).name)
    if var:
        try:
            f.set_variation_by_name(var)
        except Exception:
            pass
    return f


def report() -> dict[str, str | None]:
    """Which file each role resolves to (for `setup` checks)."""
    return {r: path(r) for r in ROLES}
