import numpy as np
import pytest

from pixelkasten.catalog.classify import classify, build_label_list


class TestClassify:
    def test_returns_labels_above_threshold(self):
        # Image embedding that's similar to label 0 but not label 1.
        image_emb = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        label_emb = np.array(
            [
                [0.9, 0.1, 0.0],  # Similar to image.
                [0.0, 0.0, 1.0],  # Orthogonal to image.
            ],
            dtype=np.float32,
        )
        # Normalize.
        for i in range(len(label_emb)):
            label_emb[i] /= np.linalg.norm(label_emb[i])

        results = classify(image_emb, label_emb, ["beach", "snow"], threshold=0.5)

        # Only "beach" should be above threshold.
        assert len(results) == 1
        assert len(results[0]) == 1
        assert results[0][0][0] == "beach"

    def test_filters_labels_below_threshold(self):
        # Two orthogonal vectors — cosine similarity is 0.
        image_emb = np.array([[1.0, 0.0]], dtype=np.float32)
        label_emb = np.array([[0.0, 1.0]], dtype=np.float32)

        results = classify(image_emb, label_emb, ["snow"], threshold=0.1)

        # Score is 0.0, below threshold of 0.1.
        assert results[0] == []

    def test_sorts_by_score_descending(self):
        image_emb = np.array([[0.7, 0.7, 0.1]], dtype=np.float32)
        image_emb /= np.linalg.norm(image_emb)

        label_emb = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.5, 0.5, 0.0],
            ],
            dtype=np.float32,
        )
        for i in range(len(label_emb)):
            label_emb[i] /= np.linalg.norm(label_emb[i])

        results = classify(
            image_emb,
            label_emb,
            ["a", "b", "c"],
            threshold=0.0,
        )

        # "c" should score highest (most aligned with image).
        scores = [s for _, s in results[0]]
        assert scores == sorted(scores, reverse=True)


class TestBuildLabelList:
    def test_applies_prompt_template_and_prefix(self):
        label_sets = {
            "scene": ["beach", "mountain"],
            "event": ["wedding"],
        }

        prefixed, prompted = build_label_list(label_sets)

        assert prefixed == ["scene:beach", "scene:mountain", "event:wedding"]
        assert prompted == [
            "a photo of beach",
            "a photo of mountain",
            "a photo of wedding",
        ]
