"""The identity of a Russian legal act, read from the top of its text.

«Закон РФ от 07.02.1992 N 2300-1 (ред. от 14.07.2022)»: type, date and number identify the
act across all of its redactions; the redaction date tells the versions apart.
"""

import re

HEADER_CHARS = 3000
_ACT_TYPE = (
    r"(?:Федеральный\s+конституционный\s+закон|Федеральный\s+закон"
    r"|Закон\s+(?:РФ|Российской\s+Федерации)|Указ\s+Президента\s+(?:РФ|Российской\s+Федерации)"
    r"|Постановление\s+Правительства\s+(?:РФ|Российской\s+Федерации)"
    r"|[А-ЯЁ][а-яё]+\s+кодекс\s+(?:РФ|Российской\s+Федерации))"
)
# The type must sit right before "от": the list of amending laws («Федеральных законов от…»)
# names other acts and must not match.
_IDENTIFIER = re.compile(
    rf"(?P<type>{_ACT_TYPE})\s+от\s+(?P<date>\d{{2}}\.\d{{2}}\.\d{{4}})\s*(?:г\.\s*)?"
    r"(?:N|№)\s*(?P<number>[0-9A-Za-zА-Яа-яЁё\-]+)",
    re.IGNORECASE,
)
_REDACTION = re.compile(r"\(\s*ред\.\s+от\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)


def law_identifier(text: str) -> str | None:
    """``"07.02.1992 N 2300-1"`` for the act at the top of ``text``, else None."""
    match = _IDENTIFIER.search(text[:HEADER_CHARS])
    if match is None:
        return None
    number = match.group("number").upper().replace("ФЗ", "-ФЗ").replace("--", "-")
    return f"{match.group('date')} N {number}"


def law_redaction(text: str) -> str | None:
    """The redaction date (``"14.07.2022"``) printed under the act's title, if any."""
    match = _REDACTION.search(text[:HEADER_CHARS])
    return match.group(1) if match else None
