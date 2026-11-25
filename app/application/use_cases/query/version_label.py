"""The ``[Doc: … | v… | …]`` line that tells the model which version a passage is from."""

from app.domain.retrieval.match_version import MatchVersion


def version_label(version: MatchVersion) -> str:
    return f"[Doc: {version.file_name} | {_versions(version)} | {_date(version)}]"


def _versions(version: MatchVersion) -> str:
    covered = version.covered_versions
    if len(covered) == 1:
        return f"v{covered[0]}"
    return f"v{covered[0]}–v{covered[-1]} (без изменений)"


def _date(version: MatchVersion) -> str:
    if version.redaction:
        return f"ред. от {version.redaction}"
    return version.created_at.date().isoformat() if version.created_at else "дата неизвестна"
