"""Typed enums shared across service boundaries."""

from enum import StrEnum


class FreshnessState(StrEnum):
    """Represents whether a metric is recent enough for the UI."""

    FRESH = "fresh"
    STALE = "stale"
    ERROR = "error"

