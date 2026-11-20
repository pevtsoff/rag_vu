from enum import StrEnum


class JobOutcome(StrEnum):
    PROCESSED = "processed"
    SKIPPED = "skipped"
    ALREADY_HANDLED = "already_handled"
