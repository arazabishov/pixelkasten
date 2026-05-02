"""
AI-powered album discovery.

Provides CLIP embedding, HDBSCAN clustering, temporal refinement, VLM
captioning, and LLM album naming. All heavy
dependencies (torch, sklearn, ollama) are deferred-imported so they are
only loaded when --discover is used.
"""

from pixelkasten.stages.discovery.discovery import run_discovery

__all__ = ["run_discovery"]
