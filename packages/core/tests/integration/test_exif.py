"""
Integration tests for exiftool.

Requires exiftool installed (`brew install exiftool`).
"""

from pixelkasten.core.exiftool import check_exiftool


class TestCheckExiftool:
    def test_does_not_raise_when_installed(self):
        # Should not raise — exiftool is a prerequisite for integration tests.
        check_exiftool()
