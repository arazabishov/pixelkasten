"""Tests for tools/similarity.py — k-NN over embeddings.npy."""

import json
import os
from unittest.mock import patch

import numpy as np
import pytest

from pixelkasten.tools.similarity import resolve_library, similar


def _make_library(tmp_path, embeddings: np.ndarray, paths: list[str]):
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    np.save(pk / "embeddings.npy", embeddings.astype(np.float32))
    (pk / "embeddings.paths.json").write_text(json.dumps(paths))
    for name in paths:
        (lib / name).write_bytes(b"\xff\xd8\xff")
    return str(lib)


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


class TestResolveLibrary:
    def test_finds_library_from_file_inside_it(self, tmp_path):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        # Walking up from a file inside the library finds the library root
        assert resolve_library(os.path.join(lib, "a.jpg")) == lib

    def test_finds_library_from_subdir(self, tmp_path):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        sub = os.path.join(lib, "sub")
        os.makedirs(sub)
        # Walking up from a deeper path still finds the library
        assert resolve_library(sub) == lib

    def test_raises_when_no_library_found(self, tmp_path):
        with pytest.raises(RuntimeError, match="No .pixelkasten/"):
            resolve_library(str(tmp_path))


class TestSimilarInLibrary:
    def test_returns_nearest_neighbors_by_cosine(self, tmp_path):
        # 3 vectors: a is close to b, c is orthogonal.
        a = _unit([1.0, 0.0, 0.0, 0.0])
        b = _unit([0.9, 0.1, 0.0, 0.0])
        c = _unit([0.0, 0.0, 1.0, 0.0])
        lib = _make_library(tmp_path, np.vstack([a, b, c]), ["a.jpg", "b.jpg", "c.jpg"])

        results = similar(os.path.join(lib, "a.jpg"), lib, k=2)

        # Top result is b (most similar non-self); c is farther
        assert results[0]["path"].endswith("b.jpg")
        assert results[1]["path"].endswith("c.jpg")
        # Scores are descending
        assert results[0]["score"] > results[1]["score"]

    def test_excludes_query_from_its_own_results(self, tmp_path):
        a = _unit([1.0, 0.0])
        b = _unit([0.5, 0.5])
        lib = _make_library(tmp_path, np.vstack([a, b]), ["a.jpg", "b.jpg"])

        results = similar(os.path.join(lib, "a.jpg"), lib, k=5)

        # Query path itself never appears in results
        assert all(not r["path"].endswith("/a.jpg") for r in results)

    def test_k_larger_than_corpus_returns_all_minus_query(self, tmp_path):
        a = _unit([1.0, 0.0])
        b = _unit([0.0, 1.0])
        lib = _make_library(tmp_path, np.vstack([a, b]), ["a.jpg", "b.jpg"])

        results = similar(os.path.join(lib, "a.jpg"), lib, k=100)

        # Only one neighbor available when k exceeds corpus
        assert len(results) == 1
        assert results[0]["path"].endswith("b.jpg")

    def test_rejects_k_zero_or_negative(self, tmp_path):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        with pytest.raises(ValueError):
            similar(os.path.join(lib, "a.jpg"), lib, k=0)


class TestSimilarExternalQuery:
    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("PIL.Image.open")
    def test_embeds_external_query_and_searches(self, mock_open, mock_embed, tmp_path):
        # Library has one vector pointing along x-axis
        lib = _make_library(tmp_path, _unit([1.0, 0.0])[None], ["a.jpg"])
        # External query is mocked to embed at the same position
        mock_embed.return_value = _unit([1.0, 0.0])[None]
        mock_open.return_value = object()

        external = tmp_path / "external.jpg"
        external.write_bytes(b"\xff\xd8\xff")
        results = similar(str(external), lib, k=5)

        # External query is embedded via embed_images; a.jpg surfaces as the only neighbor
        mock_embed.assert_called_once()
        assert len(results) == 1
        assert results[0]["path"].endswith("a.jpg")
        # Cosine similarity of identical unit vectors is 1.0
        assert results[0]["score"] == pytest.approx(1.0)


class TestSimilarValidation:
    def test_raises_when_no_embeddings(self, tmp_path):
        # Library directory exists but no embeddings files
        lib = tmp_path / "lib"
        (lib / ".pixelkasten").mkdir(parents=True)
        (lib / "a.jpg").write_bytes(b"\xff")

        with pytest.raises(RuntimeError, match="No embeddings"):
            similar(str(lib / "a.jpg"), str(lib), k=5)

    def test_raises_when_paths_and_matrix_misaligned(self, tmp_path):
        # Pre-build inconsistent state on disk to verify the safety check
        lib = tmp_path / "lib"
        pk = lib / ".pixelkasten"
        pk.mkdir(parents=True)
        np.save(pk / "embeddings.npy", np.zeros((2, 4), dtype=np.float32))
        (pk / "embeddings.paths.json").write_text(json.dumps(["one.jpg"]))
        (lib / "one.jpg").write_bytes(b"\xff")

        with pytest.raises(RuntimeError, match="doesn't match"):
            similar(str(lib / "one.jpg"), str(lib), k=5)
