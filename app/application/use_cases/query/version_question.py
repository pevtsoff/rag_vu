"""Questions about how a document changed over its versions."""

import re
from dataclasses import dataclass

_HISTORY = re.compile(
    r"(?:редакци|изменени|изменил|поменял|версии|версия|верси[ейю]|ранее|раньше|прежн|"
    r"до\s+изменени|в\s+старой|в\s+предыдущ|сравни|отличи|разниц|история)",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_VERSION_NUMBER = re.compile(r"(?:\bv|верси[яиюей]\s*(?:№|N)?\s*)(\d{1,3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class NamedVersions:
    """Versions the question points at, by redaction/upload year or version number."""

    years: frozenset[str] = frozenset()
    numbers: frozenset[int] = frozenset()


def asks_about_versions(question: str) -> bool:
    """True when the answer needs more than the latest version of a document."""
    return bool(_HISTORY.search(question))


def named_versions(question: str) -> NamedVersions:
    return NamedVersions(
        years=frozenset(_YEAR.findall(question)),
        numbers=frozenset(int(number) for number in _VERSION_NUMBER.findall(question)),
    )
