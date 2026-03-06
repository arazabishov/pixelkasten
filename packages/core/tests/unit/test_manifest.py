from pixelkasten.manifest import (
    Dedupe,
    DedupeResult,
    ManifestEntry,
    Source,
    Status,
)


def _entry(dedupe=None):
    return ManifestEntry(media_path="/a.jpg", source=Source(type="loose"), dedupe=dedupe)


class TestCanKeep:
    def test_returns_true_when_no_dedupe(self):
        assert _entry().can_keep() is True

    def test_returns_true_when_dedupe_result_is_keep(self):
        dedupe = Dedupe(status=Status.PROCESSED, result=DedupeResult.KEEP, hash="abc")
        assert _entry(dedupe).can_keep() is True

    def test_returns_false_when_dedupe_result_is_delete(self):
        dedupe = Dedupe(status=Status.PROCESSED, result=DedupeResult.DELETE, hash="abc")
        assert _entry(dedupe).can_keep() is False

    def test_returns_false_when_dedupe_status_is_error(self):
        dedupe = Dedupe(status=Status.ERROR, error="hash failed")
        assert _entry(dedupe).can_keep() is False
