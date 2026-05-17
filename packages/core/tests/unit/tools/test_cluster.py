"""Tests for tools/cluster.py — HDBSCAN over an embeddings slice."""

import json
import os
from unittest.mock import patch

import numpy as np
import pytest

from pixelkasten.tools.cluster import cluster


def _make_library(tmp_path, embeddings: np.ndarray, paths: list[str]):
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    np.save(pk / "embeddings.npy", embeddings.astype(np.float32))
    (pk / "embeddings.paths.json").write_text(json.dumps(paths))
    for name in paths:
        (lib / name).write_bytes(b"\xff\xd8\xff")
    return str(lib)


class _FakeHDBSCAN:
    """Stand-in for sklearn.cluster.HDBSCAN that returns canned labels."""

    def __init__(self, labels: list[int]):
        self._labels = np.array(labels)

    def __call__(self, **kwargs):
        return self

    def fit_predict(self, _matrix):
        return self._labels


class TestCluster:
    def test_groups_input_paths_by_hdbscan_label(self, tmp_path):
        # 4 entries: rows 0,1 in cluster 0; rows 2,3 in cluster 1.
        emb = np.eye(4, dtype=np.float32)
        lib = _make_library(tmp_path, emb, ["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
        fake = _FakeHDBSCAN([0, 0, 1, 1])

        with patch("sklearn.cluster.HDBSCAN", fake):
            result = cluster(
                [os.path.join(lib, n) for n in ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]],
                lib,
                min_cluster_size=2,
            )

        # Output is keyed by integer label and lists the matching paths
        assert sorted(result[0]) == sorted([os.path.join(lib, "a.jpg"), os.path.join(lib, "b.jpg")])
        assert sorted(result[1]) == sorted([os.path.join(lib, "c.jpg"), os.path.join(lib, "d.jpg")])

    def test_passes_through_noise_label_minus_one(self, tmp_path):
        emb = np.eye(3, dtype=np.float32)
        lib = _make_library(tmp_path, emb, ["a.jpg", "b.jpg", "c.jpg"])
        fake = _FakeHDBSCAN([0, 0, -1])

        with patch("sklearn.cluster.HDBSCAN", fake):
            result = cluster(
                [os.path.join(lib, n) for n in ["a.jpg", "b.jpg", "c.jpg"]],
                lib,
                min_cluster_size=2,
            )

        # HDBSCAN's noise bucket (-1) is preserved in the output
        assert -1 in result
        assert result[-1] == [os.path.join(lib, "c.jpg")]

    def test_warns_and_skips_paths_not_in_embeddings(self, tmp_path, capsys):
        emb = np.eye(1, dtype=np.float32)
        lib = _make_library(tmp_path, emb, ["a.jpg"])
        fake = _FakeHDBSCAN([0])

        with patch("sklearn.cluster.HDBSCAN", fake):
            result = cluster(
                [os.path.join(lib, "a.jpg"), os.path.join(lib, "missing.jpg")],
                lib,
                min_cluster_size=2,
            )

        # Missing path is reported on stderr
        err = capsys.readouterr().err
        assert "missing.jpg" in err
        # And dropped from the result
        assert result[0] == [os.path.join(lib, "a.jpg")]

    def test_empty_input_returns_empty_dict(self, tmp_path):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        assert cluster([], lib, min_cluster_size=2) == {}

    def test_all_missing_paths_returns_empty_dict(self, tmp_path, capsys):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        # Every input is missing -> no HDBSCAN call, empty result
        result = cluster(["/nope/x.jpg", "/nope/y.jpg"], lib, min_cluster_size=2)
        assert result == {}

    def test_rejects_min_cluster_size_below_two(self, tmp_path):
        lib = _make_library(tmp_path, np.zeros((1, 4)), ["a.jpg"])
        with pytest.raises(ValueError):
            cluster([os.path.join(lib, "a.jpg")], lib, min_cluster_size=1)

    def test_raises_when_embeddings_missing(self, tmp_path):
        lib = tmp_path / "lib"
        (lib / ".pixelkasten").mkdir(parents=True)
        (lib / "a.jpg").write_bytes(b"\xff")
        with pytest.raises(RuntimeError, match="No embeddings"):
            cluster([str(lib / "a.jpg")], str(lib), min_cluster_size=2)
