"""Shared progress factory helpers.

Stages take a progress factory with signature
``(label: str, total: int) -> ContextManager[Callable[[int], None]]``.
The context manager yields a ``tick(completed)`` callback the stage
calls to report progress. ``noop_progress`` is the default when no UI
is attached (scripts, tests, library use).
"""

from contextlib import contextmanager


@contextmanager
def noop_progress(_label: str, _total: int):
    """Progress factory that records nothing; signature-compatible with rich-backed factories."""

    def _tick(_completed: int) -> None:
        pass

    yield _tick
