"""Interface strings, loaded from the bundle's language packs.

The app carries no user-facing text of its own: every string lives in
locales/<lang>/app.yml. English is the base; a pack missing keys degrades
to English visibly, never silently, the same rule the skills follow.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class BundleError(Exception):
    pass


def bundle_root() -> Path:
    """The directory holding the router SKILL.md and locales/.

    Source layout puts it two levels above this package. VERBATIM_BUNDLE
    overrides for any other arrangement; packaging proper is step 6.
    """
    override = os.environ.get("VERBATIM_BUNDLE")
    candidates = [Path(override)] if override else []
    candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        if (candidate / "locales").is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    raise BundleError(
        "cannot locate the Verbatim bundle (no locales/ next to a SKILL.md); "
        "set VERBATIM_BUNDLE to the bundle directory"
    )


def _flatten(tree: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[str(name)] = value
    return flat


def _load_pack(lang: str) -> dict:
    path = bundle_root() / "locales" / lang / "app.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _flatten(data)


@dataclass
class Strings:
    lang: str
    table: dict
    missing: tuple = ()
    meta: dict = field(default_factory=dict)

    def __call__(self, key: str, **kwargs) -> str:
        text = self.table.get(key, key)
        if kwargs and isinstance(text, str):
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text


def load_strings(lang: str) -> Strings:
    base = _load_pack("en")
    if not base:
        raise BundleError("locales/en/app.yml is missing; the bundle is broken")
    meta_keys = {"language", "native_reviewed"}
    if lang == "en":
        table = base
        missing = ()
    else:
        pack = _load_pack(lang)
        table = dict(base)
        table.update({k: v for k, v in pack.items() if k not in meta_keys})
        missing = tuple(sorted(k for k in base if k not in pack and k not in meta_keys))
    meta = {k: table.pop(k, None) for k in meta_keys}
    return Strings(lang=lang, table=table, missing=missing, meta=meta)
