"""
AI-powered album discovery pipeline.

Provides CLIP embedding, HDBSCAN clustering, zero-shot classification,
temporal refinement, VLM captioning, and LLM album naming. All heavy
dependencies (torch, sklearn, ollama) are deferred-imported so they are
only loaded when --catalog is used.
"""

from pixelkasten.stages.catalog.pipeline import run_catalog

__all__ = ["run_catalog"]
