"""Shared types used across command pipelines.

Types used by more than one command pipeline live here so neither has to
import the other's types module. Today that is just `Status`, the per-entry
outcome enum that ingest's manifest entries and enrich's entries both carry.
"""

from enum import Enum


class Status(Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    ERROR = "error"
