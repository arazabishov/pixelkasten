import numpy as np
import pytest

from pixelkasten.manifest import (
    DiscoveryEntry,
    Location,
    ManifestEntry,
    Metadata,
    Source,
    Status,
    Tag,
)


def _entry(
    media_path,
    cluster,
    tags,
    dates,
    geo=None,
    location=None,
    caption=None,
    is_representative=False,
    failed=False,
):
    """Helper to build a DiscoveryEntry for discovery test fixtures."""
    metadata = (
        Metadata(
            status=Status.PROCESSED,
            dates=dates,
            geo=geo,
        )
        if dates
        else None
    )

    manifest_entry = ManifestEntry(
        media_path=media_path,
        source=Source(type="loose"),
        metadata=metadata,
        location=location,
    )

    return DiscoveryEntry(
        entry=manifest_entry,
        status=Status.ERROR if failed else Status.PROCESSED,
        cluster=cluster,
        is_representative=is_representative,
        tags=[Tag(name=t["name"], score=t["score"]) for t in tags],
        caption=caption,
    )


@pytest.fixture
def sample_manifest():
    """
    A small manifest with 10 entries covering different scenarios:
    - Entries 0-4: cluster 0, with metadata dates + GPS locations
    - Entries 5-7: cluster 1, with metadata dates, no GPS
    - Entry 8: noise (cluster -1), with metadata dates
    - Entry 9: failed status
    """
    sf_location = Location(
        name="San Francisco, California, US",
        region="California, US",
        country="US",
    )
    sunnyvale_location = Location(
        name="Sunnyvale, California, US",
        region="California, US",
        country="US",
    )

    entries = [
        _entry(
            "/photos/img_001.jpg",
            cluster=0,
            tags=[{"name": "scene:beach", "score": 0.31}],
            dates=["2019-07-15T14:30:00"],
            geo={"latitude": 37.80, "longitude": -122.41},
            location=sf_location,
            caption="A beach scene",
            is_representative=True,
        ),
        _entry(
            "/photos/img_002.jpg",
            cluster=0,
            tags=[{"name": "scene:beach", "score": 0.28}],
            dates=["2019-07-15T16:00:00"],
            geo={"latitude": 37.79, "longitude": -122.44},
            location=sf_location,
        ),
        _entry(
            "/photos/img_003.jpg",
            cluster=0,
            tags=[{"name": "scene:city street", "score": 0.25}],
            dates=["2019-07-16T10:00:00"],
            geo={"latitude": 37.40, "longitude": -122.03},
            location=sunnyvale_location,
        ),
        _entry(
            "/photos/img_004.jpg",
            cluster=0,
            tags=[],
            dates=["2019-07-17T09:00:00"],
            geo={"latitude": 37.80, "longitude": -122.41},
            location=sf_location,
            is_representative=True,
        ),
        _entry(
            "/photos/img_005.jpg",
            cluster=0,
            tags=[],
            dates=["2019-07-17T11:00:00"],
            geo={"latitude": 37.80, "longitude": -122.41},
            location=sf_location,
        ),
        _entry(
            "/photos/img_006.jpg",
            cluster=1,
            tags=[{"name": "event:dinner gathering", "score": 0.22}],
            dates=["2019-08-20T19:00:00"],
            geo=None,
            caption="A dinner gathering",
            is_representative=True,
        ),
        _entry(
            "/photos/img_007.jpg",
            cluster=1,
            tags=[{"name": "event:dinner gathering", "score": 0.20}],
            dates=["2019-08-20T20:30:00"],
            geo=None,
        ),
        _entry(
            "/photos/img_008.jpg",
            cluster=1,
            tags=[],
            dates=["2019-08-20T21:00:00"],
            geo=None,
        ),
        _entry(
            "/photos/img_009.jpg",
            cluster=-1,
            tags=[],
            dates=["2019-09-01T12:00:00"],
            geo=None,
        ),
        _entry(
            "/photos/img_010.jpg",
            cluster=None,
            tags=[],
            dates=None,
            failed=True,
        ),
    ]

    return {
        "version": 1,
        "embeddings_file": "embeddings.npy",
        "total_images": 10,
        "embedded": 9,
        "failed": 1,
        "entries": entries,
        "clusters": {
            "0": {"size": 5},
            "1": {"size": 3},
        },
    }


@pytest.fixture
def sample_embeddings():
    """
    9x768 normalized embedding matrix (matches 9 ok-status entries in sample_manifest).
    Seeded for determinism. First 5 vectors are similar (cluster 0),
    next 3 are similar (cluster 1), last 1 is different (noise).
    """
    rng = np.random.RandomState(42)

    # Create base vectors for each cluster.
    base_0 = rng.randn(768).astype(np.float32)
    base_0 /= np.linalg.norm(base_0)

    base_1 = rng.randn(768).astype(np.float32)
    base_1 /= np.linalg.norm(base_1)

    noise_vec = rng.randn(768).astype(np.float32)
    noise_vec /= np.linalg.norm(noise_vec)

    # Create variations around each base.
    embeddings = []
    for _ in range(5):
        v = base_0 + rng.randn(768).astype(np.float32) * 0.05
        v /= np.linalg.norm(v)
        embeddings.append(v)

    for _ in range(3):
        v = base_1 + rng.randn(768).astype(np.float32) * 0.05
        v /= np.linalg.norm(v)
        embeddings.append(v)

    embeddings.append(noise_vec)

    return np.array(embeddings)


@pytest.fixture
def sample_manifest_path(tmp_path, sample_manifest, sample_embeddings):
    """Writes sample embeddings to temp dir, returns tmp_path."""
    embeddings_path = tmp_path / "embeddings.npy"
    np.save(embeddings_path, sample_embeddings)

    return tmp_path
