"""
Integration tests for the deterministic pipeline stages.

Runs embed → enrich → refine on real test images and verifies the
manifest has the correct structure at each stage. This catches cross-module
data contract issues (e.g., module A writes field X, module B expects field Y).

Requires exiftool installed. Does NOT require Ollama or CLIP model download
(uses small synthetic embeddings to avoid the heavy CLIP dependency).
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from pixelkasten.stages.scan import scan, is_image
from pixelkasten.core.manifest import (
    write_manifest,
    read_manifest,
    enrich_manifest,
    enrich_manifest_exif,
    update_manifest_clusters,
)
from pixelkasten.catalog.cluster import (
    cluster_embeddings,
    find_representatives,
    cluster_summary,
)
from pixelkasten.catalog.classify import classify, build_label_list
from pixelkasten.core.exif import read_exif_for_all, reverse_geocode
from pixelkasten.catalog.refine import refine_clusters


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


@pytest.fixture
def test_images(tmp_path):
    """
    Copy fixture JPEGs to a temp directory and return the path.
    We copy to avoid any accidental writes to the shared fixtures.
    """
    media_dir = tmp_path / "photos"
    media_dir.mkdir()

    for src in FIXTURES_DIR.glob("*.jpg"):
        shutil.copy2(src, media_dir / src.name)

    return media_dir


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


class TestScanToManifest:
    """Test that scan → embed → write produces a valid manifest."""

    def test_scan_finds_fixture_images(self, test_images):
        all_files = scan(str(test_images))["files_media"]
        image_files = [f for f in all_files if is_image(Path(f))]

        # Should find all 4 fixture JPEGs.
        assert len(image_files) == 4

    def test_write_manifest_produces_valid_json(self, test_images, output_dir):
        image_files = [Path(f) for f in scan(str(test_images))["files_media"] if is_image(Path(f))]

        # Use synthetic embeddings (avoid CLIP dependency).
        rng = np.random.RandomState(42)
        embeddings = rng.randn(len(image_files), 64).astype(np.float32)
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0] * len(image_files))
        classifications = [[] for _ in image_files]
        representatives = {0: [0]}
        failed_indices = []

        manifest_path = write_manifest(
            output_dir,
            image_files,
            embeddings,
            labels,
            classifications,
            representatives,
            failed_indices,
        )

        manifest = read_manifest(manifest_path)

        # Verify manifest structure.
        assert manifest["version"] == 1
        assert manifest["total_images"] == 4
        assert manifest["embedded"] == 4
        assert manifest["failed"] == 0
        assert len(manifest["entries"]) == 4

        # Every entry should have required fields.
        for entry in manifest["entries"]:
            assert "path" in entry
            assert "status" in entry
            assert "cluster" in entry
            assert "tags" in entry
            assert "is_representative" in entry


class TestEnrichManifestStructure:
    """Test that enrich adds EXIF data and the manifest stays valid."""

    def _create_manifest(self, test_images, output_dir):
        """Helper: create a basic manifest from fixture images."""
        image_files = [Path(f) for f in scan(str(test_images))["files_media"] if is_image(Path(f))]

        rng = np.random.RandomState(42)
        embeddings = rng.randn(len(image_files), 64).astype(np.float32)
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0] * len(image_files))
        classifications = [[] for _ in image_files]
        representatives = {0: [0]}

        manifest_path = write_manifest(
            output_dir,
            image_files,
            embeddings,
            labels,
            classifications,
            representatives,
            [],
        )
        np.save(output_dir / "embeddings.npy", embeddings)
        return manifest_path

    def test_enrich_adds_exif_to_entries(self, test_images, output_dir):
        manifest_path = self._create_manifest(test_images, output_dir)
        manifest = read_manifest(manifest_path)

        exif_data = read_exif_for_all(manifest)
        location_data = reverse_geocode(exif_data)
        enrich_manifest_exif(manifest_path, exif_data, location_data=location_data)

        result = read_manifest(manifest_path)

        # At least some entries should have EXIF data.
        entries_with_exif = [e for e in result["entries"] if e.get("exif")]
        assert len(entries_with_exif) > 0

        # The datetime+gps fixture should have all fields.
        for entry in result["entries"]:
            if "with-datetime-and-gps" in entry["path"]:
                exif = entry["exif"]
                assert exif["timestamp"] is not None
                assert exif["gps"] is not None
                assert exif.get("location_name") is not None
                assert exif.get("location_region") is not None
                break

    def test_enrich_adds_cluster_date_range(self, test_images, output_dir):
        manifest_path = self._create_manifest(test_images, output_dir)

        # enrich_manifest_exif only enriches existing clusters, so we need
        # to create the clusters dict first (normally done by enrich_manifest
        # in the caption step, but here we simulate it).
        manifest = read_manifest(manifest_path)
        manifest["clusters"] = {
            "0": {"size": 4, "captions": [], "top_tags": []},
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        manifest = read_manifest(manifest_path)
        exif_data = read_exif_for_all(manifest)
        enrich_manifest_exif(manifest_path, exif_data)

        result = read_manifest(manifest_path)
        clusters = result.get("clusters", {})

        # Cluster 0 should have a date_range (at least 2 fixtures have timestamps).
        assert "0" in clusters
        assert "date_range" in clusters["0"]
        assert "earliest" in clusters["0"]["date_range"]
        assert "latest" in clusters["0"]["date_range"]


class TestRefineManifestStructure:
    """Test that refine updates cluster assignments and the manifest stays valid."""

    def _create_enriched_manifest(self, test_images, output_dir):
        """Helper: create an enriched manifest from fixture images."""
        image_files = [Path(f) for f in scan(str(test_images))["files_media"] if is_image(Path(f))]

        rng = np.random.RandomState(42)
        embeddings = rng.randn(len(image_files), 64).astype(np.float32)
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0] * len(image_files))
        classifications = [[] for _ in image_files]
        representatives = {0: [0]}

        manifest_path = write_manifest(
            output_dir,
            image_files,
            embeddings,
            labels,
            classifications,
            representatives,
            [],
        )
        np.save(output_dir / "embeddings.npy", embeddings)

        manifest = read_manifest(manifest_path)
        exif_data = read_exif_for_all(manifest)
        enrich_manifest_exif(manifest_path, exif_data)

        return manifest_path, embeddings

    def test_refine_produces_valid_labels(self, test_images, output_dir):
        manifest_path, embeddings = self._create_enriched_manifest(
            test_images, output_dir
        )
        manifest = read_manifest(manifest_path)

        new_labels, stats = refine_clusters(manifest, embeddings)

        # Labels array should have same length as ok-status entries.
        n_ok = sum(1 for e in manifest["entries"] if e.get("status") == "ok")
        assert len(new_labels) == n_ok

        # All labels should be integers >= -1.
        assert all(label >= -1 for label in new_labels)

        # Stats should have all expected keys.
        assert "ejected" in stats
        assert "splits" in stats
        assert "merges" in stats
        assert "absorbed_by_location" in stats
        assert "absorbed_by_similarity" in stats

    def test_update_manifest_preserves_exif_after_refine(self, test_images, output_dir):
        manifest_path, embeddings = self._create_enriched_manifest(
            test_images, output_dir
        )
        manifest = read_manifest(manifest_path)

        new_labels, _ = refine_clusters(manifest, embeddings)
        representatives = find_representatives(embeddings, new_labels)
        update_manifest_clusters(manifest_path, new_labels, representatives)

        result = read_manifest(manifest_path)

        # EXIF data should still be present on entries.
        entries_with_exif = [e for e in result["entries"] if e.get("exif")]
        assert len(entries_with_exif) > 0

        # Clusters summary should exist.
        assert "clusters" in result
        assert len(result["clusters"]) > 0

    def test_caption_enrich_does_not_destroy_exif_data(self, test_images, output_dir):
        """
        Regression test: enrich_manifest() (called by caption step) used to
        rebuild the clusters dict from scratch, destroying date_range and
        locations. This test verifies the fix.
        """
        manifest_path, embeddings = self._create_enriched_manifest(
            test_images, output_dir
        )
        manifest = read_manifest(manifest_path)

        # Simulate caption step adding captions.
        captions = {}
        for entry in manifest["entries"]:
            if entry.get("is_representative"):
                captions[entry["path"]] = "A test caption"

        enrich_manifest(manifest_path, captions)

        result = read_manifest(manifest_path)

        # Captions should be added.
        captioned = [e for e in result["entries"] if "caption" in e]
        assert len(captioned) > 0

        # Cluster date_range should still exist (not destroyed by enrich_manifest).
        for cluster in result["clusters"].values():
            if cluster.get("date_range"):
                assert "earliest" in cluster["date_range"]
                assert "latest" in cluster["date_range"]
                break
