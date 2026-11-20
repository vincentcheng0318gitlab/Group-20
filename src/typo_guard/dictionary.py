"""Optional spelling variants and supplemental vocabulary for typo-guard.

The base spell checker remains the bundled American-English dictionary.  The
British-English view accepts common UK-to-US spelling variants when their
American equivalent exists in that dictionary.  Project-specific words can be
added without mutating the cached base dictionary.
"""
from __future__ import annotations

from typing import Any, Iterable


_UK_IRREGULAR_TO_US = {
    "ageing": ("aging",),
    "aeroplane": ("airplane",),
    "aluminium": ("aluminum",),
    "burnt": ("burned",),
    "cheque": ("check",),
    "cheques": ("checks",),
    "cosy": ("cozy",),
    "grey": ("gray",),
    "jewellery": ("jewelry",),
    "learnt": ("learned",),
    "maths": ("math",),
    "mould": ("mold",),
    "mouldy": ("moldy",),
    "plough": ("plow",),
    "practise": ("practice",),
    "practised": ("practiced",),
    "practising": ("practicing",),
    "programme": ("program",),
    "programmes": ("programs",),
    "sceptic": ("skeptic",),
    "sulphur": ("sulfur",),
    "theatre": ("theater",),
    "theatres": ("theaters",),
    "tyre": ("tire",),
    "tyres": ("tires",),
}

_SUFFIX_PAIRS = (
    ("isations", "izations"),
    ("isation", "ization"),
    ("ising", "izing"),
    ("ised", "ized"),
    ("ises", "izes"),
    ("iser", "izer"),
    ("ise", "ize"),
    ("ysing", "yzing"),
    ("ysed", "yzed"),
    ("yses", "yzes"),
    ("yse", "yze"),
    ("ogue", "og"),
    ("ence", "ense"),
    ("re", "er"),
)
_DOUBLE_L_SUFFIXES = ("ing", "ed", "er", "or", "ance", "ant", "ous")


def _american_spellings(word: str) -> set[str]:
    """Return plausible American-English forms of a British spelling."""
    forms = set(_UK_IRREGULAR_TO_US.get(word, ()))

    if "our" in word:
        forms.add(word.replace("our", "or"))
    if "sation" in word:
        forms.add(word.replace("sation", "zation"))

    for british, american in _SUFFIX_PAIRS:
        if word.endswith(british) and len(word) > len(british):
            forms.add(word[:-len(british)] + american)

    for suffix in _DOUBLE_L_SUFFIXES:
        if word.endswith("ll" + suffix):
            forms.add(word[:-len(suffix) - 1] + suffix)

    for pair in ("ae", "oe"):
        if pair in word:
            forms.add(word.replace(pair, "e"))

    return forms


class _DictionaryView:
    """A non-mutating view over the cached spell checker."""

    def __init__(self, base: Any, additional_words: set[str], british: bool) -> None:
        self._base = base
        self._additional_words = additional_words
        self._british = british

    def __contains__(self, word: str) -> bool:
        if word in self._additional_words or word in self._base:
            return True
        if self._british:
            return any(form in self._base for form in _american_spellings(word))
        return False

    def candidates(self, word: str):
        return self._base.candidates(word)

    def word_usage_frequency(self, word: str) -> int:
        return self._base.word_usage_frequency(word)


def configured_dictionary(
    base: Any,
    *,
    language: str = "en-US",
    additional_words: Iterable[str] = (),
) -> Any:
    """Return the base dictionary or an overlay for language/custom words.

    ``en-GB`` accepts common British spellings by checking their American
    equivalents. ``additional_words`` adds words without changing the shared
    cached spell checker used by default runs.
    """
    if language not in {"en-US", "en-GB"}:
        raise ValueError("language must be 'en-US' or 'en-GB'")
    if isinstance(additional_words, str):
        additional_words = (additional_words,)
    extras = {word.strip().lower() for word in additional_words if word.strip()}
    british = language == "en-GB"
    if not british and not extras:
        return base
    return _DictionaryView(base, extras, british)
