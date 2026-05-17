"""
Unit tests for the Ollama tool wrapper.
"""

from unittest.mock import patch, MagicMock

import pytest

from pixelkasten.utils.ollama import check_ollama, chat


class TestCheckOllama:
    @patch("ollama.list")
    def test_raises_when_model_not_found(self, mock_list):
        mock_list.return_value = MagicMock(models=[MagicMock(model="gemma4:e4b")])

        with pytest.raises(RuntimeError, match="Model 'missing' not found"):
            check_ollama("missing")

    @patch("ollama.list")
    def test_accepts_full_model_name(self, mock_list):
        mock_list.return_value = MagicMock(models=[MagicMock(model="gemma4:e4b")])

        # Should not raise.
        check_ollama("gemma4:e4b")

    @patch("ollama.list")
    def test_accepts_base_model_name(self, mock_list):
        mock_list.return_value = MagicMock(models=[MagicMock(model="gemma4:e4b")])

        # Should match base name without tag.
        check_ollama("gemma4")

    @patch("ollama.list")
    def test_raises_when_ollama_not_running(self, mock_list):
        mock_list.side_effect = ConnectionError("refused")

        with pytest.raises(RuntimeError, match="Ollama is not running"):
            check_ollama("gemma4:e4b")


class TestChat:
    @patch("ollama.chat")
    def test_returns_stripped_response(self, mock_chat):
        response = MagicMock()
        response.message.content = "  A sunset over the ocean.  "
        mock_chat.return_value = response

        result = chat("gemma4:e4b", "Describe this.")

        assert result == "A sunset over the ocean."

    @patch("ollama.chat")
    def test_returns_none_for_empty_content(self, mock_chat):
        response = MagicMock()
        response.message.content = ""
        mock_chat.return_value = response

        assert chat("gemma4:e4b", "Describe this.") is None

    @patch("ollama.chat")
    def test_passes_images_for_vision_models(self, mock_chat):
        response = MagicMock()
        response.message.content = "A photo."
        mock_chat.return_value = response

        chat("gemma4:e4b", "Describe this.", images=["/photos/img.jpg"])

        # Verify the images were passed in the message.
        call_args = mock_chat.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["images"] == ["/photos/img.jpg"]

    @patch("ollama.chat")
    def test_omits_images_key_when_none(self, mock_chat):
        response = MagicMock()
        response.message.content = "Response."
        mock_chat.return_value = response

        chat("gemma4:e4b", "Hello.")

        messages = mock_chat.call_args.kwargs["messages"]
        assert "images" not in messages[0]
