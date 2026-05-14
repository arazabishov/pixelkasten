"""
Unit tests for the caption module with mocked Ollama.
"""

from unittest.mock import patch

from pixelkasten.manifest import Discovery, ManifestEntry, Source, Status
from pixelkasten.stages.discovery.caption import (
    caption_image,
    caption_representatives,
)


def _entry(path, is_representative=False, status=Status.PROCESSED):
    return ManifestEntry(
        media_path=path,
        source=Source(type="loose"),
        discovery=Discovery(
            status=status,
            cluster=0,
            is_representative=is_representative,
        ),
    )


class TestCaptionImage:
    @patch("pixelkasten.stages.discovery.caption._downscale", return_value=b"fake-jpeg")
    @patch("pixelkasten.stages.discovery.caption.chat")
    def test_returns_caption(self, mock_chat, mock_downscale):
        mock_chat.return_value = "A sunset over the ocean."

        result = caption_image("gemma4:e4b", "/photos/img.jpg", "Describe this.")

        assert result == "A sunset over the ocean."

        # Verify downscaled bytes were passed to chat.
        mock_chat.assert_called_once_with("gemma4:e4b", "Describe this.", images=[b"fake-jpeg"])

    @patch("pixelkasten.stages.discovery.caption._downscale", return_value=b"fake-jpeg")
    @patch("pixelkasten.stages.discovery.caption.chat")
    def test_returns_none_on_exception(self, mock_chat, mock_downscale):
        mock_chat.side_effect = RuntimeError("Connection refused")

        result = caption_image("gemma4:e4b", "/photos/img.jpg", "Describe this.")

        assert result is None

    @patch("pixelkasten.stages.discovery.caption._downscale", return_value=b"fake-jpeg")
    @patch("pixelkasten.stages.discovery.caption.chat")
    def test_returns_none_for_empty_content(self, mock_chat, mock_downscale):
        mock_chat.return_value = None

        result = caption_image("gemma4:e4b", "/photos/img.jpg", "Describe this.")

        assert result is None


class TestCaptionRepresentatives:
    @patch("pixelkasten.stages.discovery.caption.caption_image")
    def test_captions_only_representatives(self, mock_caption):
        mock_caption.return_value = "A beach scene."

        entries = [
            _entry("/photos/a.jpg", is_representative=True),
            _entry("/photos/b.jpg", is_representative=False),
            _entry("/photos/c.jpg", is_representative=True),
        ]

        captions = caption_representatives(entries, "gemma4:e4b")

        # Only representatives should be captioned.
        assert len(captions) == 2
        assert "/photos/a.jpg" in captions
        assert "/photos/c.jpg" in captions
        assert "/photos/b.jpg" not in captions

    @patch("pixelkasten.stages.discovery.caption.caption_image")
    def test_skips_failed_entries(self, mock_caption):
        mock_caption.return_value = "A beach scene."

        entries = [
            _entry("/photos/a.jpg", is_representative=True, status=Status.ERROR),
            _entry("/photos/b.jpg", is_representative=True, status=Status.PROCESSED),
        ]

        captions = caption_representatives(entries, "gemma4:e4b")

        # Only the processed entry should be captioned.
        assert len(captions) == 1
        assert "/photos/b.jpg" in captions

    @patch("pixelkasten.stages.discovery.caption.caption_image")
    def test_excludes_failed_captions(self, mock_caption):
        mock_caption.side_effect = [None, "A dinner scene."]

        entries = [
            _entry("/photos/a.jpg", is_representative=True),
            _entry("/photos/b.jpg", is_representative=True),
        ]

        captions = caption_representatives(entries, "gemma4:e4b")

        # Only successfully captioned images appear.
        assert len(captions) == 1
        assert "/photos/b.jpg" in captions

    @patch("pixelkasten.stages.discovery.caption.caption_image")
    def test_calls_progress_callback(self, mock_caption):
        mock_caption.return_value = "A scene."
        progress_calls = []

        entries = [
            _entry("/photos/a.jpg", is_representative=True),
            _entry("/photos/b.jpg", is_representative=True),
        ]

        caption_representatives(
            entries, "gemma4:e4b", on_progress=lambda n: progress_calls.append(n)
        )

        assert progress_calls == [1, 2]
