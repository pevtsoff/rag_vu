"""Stable ltree labels derived from (often Cyrillic) heading text."""

import re
import unicodedata

_CYRILLIC = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщыэюя",
        "a b v g d e e zh z i i k l m n o p r s t u f kh ts ch sh shch y e yu ya".split(),
        strict=True,
    )
)
# Hard and soft signs have no Latin counterpart.
_CYRILLIC.update({"ъ": "", "ь": ""})
MAX_LABEL_LENGTH = 200


def ltree_label(value: str, fallback: str) -> str:
    """Return a label of ``[a-z0-9_]`` characters that starts with a letter."""
    transliterated = "".join(_CYRILLIC.get(char, char) for char in value.lower())
    ascii_text = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode()
    label = re.sub(r"[^a-z0-9_]+", "_", ascii_text.lower()).strip("_")
    if not label or not label[0].isalpha():
        label = f"{fallback}_{label}" if label else fallback
    return label[:MAX_LABEL_LENGTH]
