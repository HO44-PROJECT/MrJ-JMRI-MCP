"""Hand-rolled i18n: dotted-key lookup against per-language JSON files.

No gettext, no external i18n library — per-language JSON files
(en.json/fr.json) plus str.format()-based interpolation, chosen because
existing error templates already use {query!r}-style conversion flags
that str.format supports natively.

Language selection is the JMRI_MCP_LANG env var, defaulting to "en" —
this describes this tool's runtime users, not the maintainer (who chats
in French), matching every other convention in this repo (code,
docstrings, README) and the existing JMRI_URL env-var idiom in
jmri_mcp.config.
"""

import json
import os
from pathlib import Path
from typing import Any

_SUPPORTED_LANGS = ("en", "fr")
_DEFAULT_LANG = "en"

_DIR = Path(__file__).parent
_cache: dict[str, dict[str, Any]] = {}


def _load(lang: str) -> dict[str, Any]:
    if lang not in _cache:
        with open(_DIR / f"{lang}.json", encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def active_lang() -> str:
    """JMRI_MCP_LANG env var if set and supported, else 'en'."""
    lang = os.environ.get("JMRI_MCP_LANG", _DEFAULT_LANG).strip().lower()
    return lang if lang in _SUPPORTED_LANGS else _DEFAULT_LANG


def _expand_kind(lang: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Resolve a 'kind' kwarg (e.g. "turnout") to {kind}/{kind_plural}/{Kind} via the kinds table.

    Lets one error template ("Unknown {kind} ...") serve every domain
    (turnout/light/sensor/...) while still rendering French plurals
    ("aiguillages") correctly instead of a naive kind+"s".
    """
    kind = kwargs.get("kind")
    if kind is None:
        return kwargs
    table = _load(lang).get("kinds", {})
    entry = table.get(kind, {"singular": kind, "plural": f"{kind}s", "Singular": kind.capitalize()})
    expanded = dict(kwargs)
    expanded["kind"] = entry["singular"]
    expanded["kind_plural"] = entry["plural"]
    expanded["Kind"] = entry["Singular"]
    return expanded


def lookup(lang: str, key: str, **kwargs: Any) -> str:
    """Resolve a dotted key (e.g. 'errors.unknown_entity'), formatted with kwargs.

    Falls back lang -> "en" -> the raw key itself, and never raises: a
    missing translation degrades to readable English instead of crashing,
    and a missing key entirely is visible/greppable in output (the raw
    dotted key) instead of silently swallowed.
    """
    for candidate in (lang, _DEFAULT_LANG):
        try:
            data = _load(candidate)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        node: Any = data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if isinstance(node, str):
            try:
                return node.format(**_expand_kind(candidate, kwargs))
            except (KeyError, IndexError):
                return node
    return key


def t(key: str, **kwargs: Any) -> str:
    """lookup() against the current active_lang() — the everyday call."""
    return lookup(active_lang(), key, **kwargs)


def error(exc: Any) -> str:
    """Render a JmriError for CLI display: prefix + translated errors.<code> body.

    Takes the exception itself (not just its code) so kwargs travel with it —
    callers just do `print(i18n.error(exc), file=sys.stderr)` instead of
    re-extracting .code/.kwargs at every catch site.
    """
    lang = active_lang()
    message = lookup(lang, f"errors.{exc.code}", **exc.kwargs)
    return t("cli.error_prefix", message=message)
