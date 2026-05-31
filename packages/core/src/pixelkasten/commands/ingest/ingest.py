"""
Ingest command — normalize a source into a working library.

The command runs a linear pipeline of stages:

    scan → link → dedupe → reconcile → group → emit

Each stage enriches an in-memory manifest; only ``emit`` (and ``reconcile``,
read-only) touches the filesystem. ``ingest`` threads a single ``Ingest`` state
through the stages and returns it — there is no separate result type.

The user-facing command name is ``pixelkasten import``; the Python module is
``ingest`` because ``import`` is a reserved keyword.
"""

from collections.abc import Callable

from pixelkasten.commands.ingest.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.commands.ingest.stages.emit import emit
from pixelkasten.commands.ingest.stages.group import group
from pixelkasten.commands.ingest.stages.link import link
from pixelkasten.commands.ingest.stages.reconcile import reconcile
from pixelkasten.commands.ingest.stages.report import report
from pixelkasten.commands.ingest.stages.scan import scan
from pixelkasten.configuration import IngestOptions
from pixelkasten.commands.ingest.types import Ingest


def ingest(options: IngestOptions, progress: Callable) -> Ingest:
    """Run the ingest pipeline; return the ``Ingest`` state covering every stage."""

    state = Ingest()

    # Walk the source and partition files into media / Takeout sidecars / album markers.
    state.raw_collections = scan(options.source)

    # Match each media file to its Google Takeout sidecar (archive mode short-circuits).
    link_result = link(state.raw_collections, options)
    state.manifest, state.link_stats = link_result["manifest"], link_result["stats"]

    if not options.skip_dedupe:
        # SHA-256 hash every file to identify duplicates.
        dedupe_hash(state.manifest, progress)

        # Resolve duplicates per --prefer (Takeout) or lex-smallest (archive).
        dedupe_resolve(state.manifest, options)

    # Read disk EXIF, queue write_tags for any metadata only the sidecar has.
    reconcile(state.manifest, options, progress)

    # Assign a shared group_id to logical asset groups (Live Photo siblings, edited variants).
    group(state.manifest, options)

    if not options.dry_run:
        # Copy files to the destination, write per-asset records, apply queued EXIF tags.
        emit(state.manifest, options, progress)

    if not options.dry_run:
        # Per-file CSV summary of what happened to each entry.
        report(state.manifest, options)

    return state
