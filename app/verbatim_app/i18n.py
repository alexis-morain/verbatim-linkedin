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


#: Where a wheel puts the bundle: inside the package, because an installation
#: has nothing two levels up to find. The name starts with an underscore so
#: nobody mistakes it for a directory to edit.
PACKAGED = "_bundle"


def bundle_root(package=None) -> Path:
    """The directory holding the router SKILL.md, locales/, skills/,
    references/ and the two lib/ scripts.

    Three places, tried in this order:

    1. `VERBATIM_BUNDLE`, for any arrangement neither of the others covers.
       A value naming no bundle falls through rather than stopping the app:
       a stale export is not a reason to refuse to run in a tree that is
       complete.
    2. Two levels above this package, which is a checkout.
    3. `_bundle` inside this package, which is what a wheel carries.

    The checkout comes before the packaged copy on purpose. An editable
    install has both, and the tree somebody is editing is the one they mean;
    a snapshot that shadowed it would serve yesterday's language pack and say
    nothing about it.
    """
    here = Path(package) if package else Path(__file__).resolve().parent
    override = os.environ.get("VERBATIM_BUNDLE")
    candidates = [Path(override)] if override else []
    candidates += [here.resolve().parents[1], here.resolve() / PACKAGED]
    for candidate in candidates:
        if (candidate / "locales").is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    raise BundleError(
        "cannot locate the Verbatim bundle (no locales/ next to a SKILL.md); "
        "set VERBATIM_BUNDLE to the bundle directory"
    )


@dataclass(frozen=True)
class Pack:
    """One language pack, as a chooser needs it.

    `reviewed` is the pack's own `native_reviewed` claim and not a judgement
    made here: a pack nobody who speaks the language has read still works,
    and saying so is the difference between a choice and a surprise.
    """
    code: str
    reviewed: bool = False


def _locales(root=None) -> Path:
    """Where the packs live. One spelling, because three callers below want
    it and a bundle root is a thing this module is handed as often as it
    resolves one."""
    return Path(root or bundle_root()) / "locales"


def pack_dirs(root=None) -> tuple:
    """Every language directory in the bundle, sorted.

    The rule about what one is, stated once and read from the tree: a
    directory under `locales/` whose name does not start with an underscore,
    because `_template` is the contract a translator copies and nobody is
    interviewed in it. Reading the tree rather than a list in this file is
    what makes installing a pack enough to be offered it, and what stops a
    pack that vanished from being offered on the next reload.

    `tools.available_langs` is the other caller and takes a bundle root of
    its own, which is why this does too.

    A bundle with no `locales/` at all comes back empty rather than raising.
    `bundle_root` refuses to resolve a directory that has none, so the case
    needs a root handed in from elsewhere; empty is what the settings screen
    turns into a sentence saying the bundle is broken, which is louder than a
    traceback on a screen nobody can read.
    """
    home = _locales(root)
    return tuple(sorted(path for path in (home.iterdir() if home.is_dir() else ())
                        if path.is_dir() and not path.name.startswith("_")))


def packs(root=None) -> tuple:
    """`pack_dirs` again, each one carrying what it claims about itself.

    A directory with no `app.yml` is still a pack: the skills read `style.md`
    and `market.md` out of it, and a missing interface file is the documented
    degradation, English on screen and a banner saying the pack is
    incomplete. Refusing it here would hide a pack that works.
    """
    return tuple(Pack(code=path.name,
                      reviewed=bool(_load_pack(path.name, root)
                                    .get("native_reviewed")))
                 for path in pack_dirs(root))


def _flatten(tree: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[str(name)] = value
    return flat


def _load_pack(lang: str, root=None) -> dict:
    """One pack's interface strings, flattened. Missing is legal: the English
    ones show and the app says the pack is incomplete.

    It takes a root for the same reason `pack_dirs` does. Resolving one of its
    own would read the installed bundle while its caller walked another, which
    is the shape of bug that reads correctly and answers about the wrong tree.
    """
    path = _locales(root) / lang / "app.yml"
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
