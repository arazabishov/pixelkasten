"""Import command — normalize a source into a working library.

The command runs a linear pipeline:

    scan → link → dedupe → reconcile → group → emit

Each stage enriches an in-memory manifest; only ``emit`` (and ``reconcile``,
read-only) touches the filesystem. ``run_import`` composes them and returns
an ``ImportResult`` covering every stage.
"""

from pixelkasten.commands.import_.run import ImportResult, run_import

__all__ = ["ImportResult", "run_import"]
