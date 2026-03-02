from pixelkasten.core.manifest import can_keep


class TestCanKeep:
    def test_returns_true_when_no_dedupe_key(self):
        assert can_keep({"mediaPath": "/a.jpg"}) is True

    def test_returns_true_when_dedupe_status_is_keep(self):
        assert can_keep({"dedupe": {"status": "keep"}}) is True

    def test_returns_false_when_dedupe_status_is_delete(self):
        assert can_keep({"dedupe": {"status": "delete"}}) is False

    def test_returns_false_when_dedupe_status_is_error(self):
        assert can_keep({"dedupe": {"status": "error"}}) is False
