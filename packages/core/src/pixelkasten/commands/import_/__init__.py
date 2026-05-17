"""Import command — normalize a source into a working library.

The command runs a linear pipeline:

    scan → link → dedupe → reconcile → group → emit

Each stage enriches an in-memory manifest; only ``emit`` (and ``reconcile``,
read-only) touches the filesystem. ``run`` composes them.
"""

from pixelkasten.commands.import_.run import run_import

__all__ = ["run_import"]
