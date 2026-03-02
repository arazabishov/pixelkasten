import json
import numpy as np
import pytest

from pixelkasten.core.manifest import (
    write_manifest,
    read_manifest,
    enrich_manifest,
    enrich_manifest_exif,
    update_manifest_clusters,
)


class TestWriteAndReadManifest:
    def test_round_trip(self, tmp_path):
        image_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        embeddings = np.random.randn(2, 64).astype(np.float32)
        labels = np.array([0, 0])
        classifications = [
            [("scene:beach", 0.31)],
            [("scene:beach", 0.28)],
        ]
        representatives = {0: [0]}
        failed_indices = []

        manifest_path = write_manifest(
            tmp_path,
            image_paths,
            embeddings,
            labels,
            classifications,
            representatives,
            failed_indices,
        )

        manifest = read_manifest(manifest_path)

        assert manifest["version"] == 1
        assert manifest["total_images"] == 2
        assert manifest["embedded"] == 2
        assert manifest["failed"] == 0
        assert len(manifest["entries"]) == 2

    def test_handles_failed_indices(self, tmp_path):
        image_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg", tmp_path / "c.jpg"]
        # Only 2 embeddings (index 1 failed).
        embeddings = np.random.randn(2, 64).astype(np.float32)
        labels = np.array([0, 0])
        classifications = [
            [("scene:beach", 0.3)],
            [],
        ]
        representatives = {0: [0]}
        failed_indices = [1]

        manifest_path = write_manifest(
            tmp_path,
            image_paths,
            embeddings,
            labels,
            classifications,
            representatives,
            failed_indices,
        )

        manifest = read_manifest(manifest_path)

        assert manifest["failed"] == 1
        assert manifest["entries"][1]["status"] == "failed"
        assert manifest["entries"][1]["cluster"] is None
        # Non-failed entries should have correct clusters.
        assert manifest["entries"][0]["status"] == "ok"
        assert manifest["entries"][2]["status"] == "ok"


class TestEnrichManifest:
    def test_adds_captions_without_destroying_exif(self, tmp_path):
        manifest = {
            "version": 1,
            "entries": [
                {
                    "path": "/photos/a.jpg",
                    "status": "ok",
                    "cluster": 0,
                    "tags": [],
                    "is_representative": True,
                    "exif": {
                        "timestamp": "2019-07-15T14:30:00",
                        "gps": {"latitude": 37.8, "longitude": -122.4},
                        "camera": "iPhone",
                    },
                },
                {
                    "path": "/photos/b.jpg",
                    "status": "ok",
                    "cluster": 0,
                    "tags": [],
                    "is_representative": False,
                },
            ],
            "clusters": {
                "0": {
                    "size": 2,
                    "captions": [],
                    "top_tags": [],
                    "date_range": {
                        "earliest": "2019-07-15T14:30:00",
                        "latest": "2019-07-15T14:30:00",
                    },
                    "locations": [{"latitude": 37.8, "longitude": -122.4}],
                },
            },
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        captions = {"/photos/a.jpg": "A beach in San Francisco"}
        enrich_manifest(manifest_path, captions)

        result = read_manifest(manifest_path)

        # Caption was added.
        assert result["entries"][0]["caption"] == "A beach in San Francisco"

        # EXIF data preserved on entries.
        assert result["entries"][0]["exif"]["timestamp"] == "2019-07-15T14:30:00"

        # Cluster date_range and locations preserved.
        assert "date_range" in result["clusters"]["0"]
        assert "locations" in result["clusters"]["0"]


class TestEnrichManifestExif:
    def test_adds_exif_and_location_data(self, tmp_path):
        manifest = {
            "version": 1,
            "entries": [
                {
                    "path": "/photos/a.jpg",
                    "status": "ok",
                    "cluster": 0,
                    "tags": [],
                    "is_representative": True,
                },
            ],
            "clusters": {
                "0": {
                    "size": 1,
                    "captions": [],
                    "top_tags": [],
                },
            },
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        exif_data = {
            "/photos/a.jpg": {
                "timestamp": "2019-07-15T14:30:00",
                "gps": {"latitude": 37.8, "longitude": -122.4, "altitude": 10.0},
                "camera": "iPhone 11",
            },
        }
        location_data = {
            "/photos/a.jpg": {
                "city": "San Francisco",
                "region": "California",
                "country": "US",
                "display_name": "San Francisco, California, US",
            },
        }

        enrich_manifest_exif(manifest_path, exif_data, location_data=location_data)

        result = read_manifest(manifest_path)

        # EXIF added to entry.
        assert result["entries"][0]["exif"]["timestamp"] == "2019-07-15T14:30:00"
        assert (
            result["entries"][0]["exif"]["location_name"]
            == "San Francisco, California, US"
        )
        assert result["entries"][0]["exif"]["location_region"] == "California, US"

        # Cluster summary enriched.
        assert "date_range" in result["clusters"]["0"]
        assert (
            result["clusters"]["0"]["date_range"]["earliest"] == "2019-07-15T14:30:00"
        )


class TestUpdateManifestClusters:
    def test_overwrites_labels_and_rebuilds_summaries(self, tmp_path, sample_manifest):
        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(sample_manifest, f)

        # Reassign: move all ok entries to cluster 0.
        new_labels = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0])
        representatives = {0: [0, 1, 2]}

        update_manifest_clusters(manifest_path, new_labels, representatives)

        result = read_manifest(manifest_path)

        # All ok entries should be cluster 0.
        for entry in result["entries"]:
            if entry["status"] == "ok":
                assert entry["cluster"] == 0

        # Only one cluster in summary.
        assert len(result["clusters"]) == 1
        assert result["clusters"]["0"]["size"] == 9

    def test_clears_stale_captions_on_non_representatives(self, tmp_path):
        manifest = {
            "version": 1,
            "entries": [
                {
                    "path": "/photos/a.jpg",
                    "status": "ok",
                    "cluster": 0,
                    "tags": [],
                    "is_representative": True,
                    "caption": "Old caption",
                },
                {
                    "path": "/photos/b.jpg",
                    "status": "ok",
                    "cluster": 0,
                    "tags": [],
                    "is_representative": True,
                    "caption": "Another caption",
                },
            ],
            "clusters": {
                "0": {
                    "size": 2,
                    "captions": ["Old caption", "Another caption"],
                    "top_tags": [],
                },
            },
            "embeddings_file": "embeddings.npy",
        }

        manifest_path = tmp_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Entry 0 stays representative, entry 1 does not.
        new_labels = np.array([0, 0])
        representatives = {0: [0]}

        update_manifest_clusters(manifest_path, new_labels, representatives)

        result = read_manifest(manifest_path)

        # Entry 0 keeps caption (still a representative).
        assert "caption" in result["entries"][0]

        # Entry 1 loses caption (no longer a representative).
        assert "caption" not in result["entries"][1]
