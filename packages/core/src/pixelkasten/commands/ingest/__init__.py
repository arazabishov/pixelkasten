"""Ingest command — see ``ingest.py`` for the orchestrator."""

from pixelkasten.commands.ingest.ingest import ingest
from pixelkasten.commands.ingest.types import IngestResult

__all__ = ["IngestResult", "ingest"]
