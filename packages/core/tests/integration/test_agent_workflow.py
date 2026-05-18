"""
End-to-end integration test for the agent-driven flow:
    init  →  enrich (mocked CLIP)  →  propose  →  apply --to

Mocks CLIP embedding and the reverse_geocoder so the test stays offline.
The propose step is what an agent would call; we just invoke the tool
directly.
"""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from helpers import make_options, noop_progress
from pixelkasten.configuration import ExportOptions, EnrichOptions
from pixelkasten.commands.ingest import ingest
from pixelkasten.commands.enrich import enrich
from pixelkasten.commands.export import export as run_export
from pixelkasten.utils.exiftool import check_exiftool
from pixelkasten.commands.propose import propose

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(not _has_exiftool, reason="exiftool not installed")


def _build_takeout_source(source: Path) -> None:
    """A minimal Takeout source: one album-bound photo and one loose."""
    folder = source / "Photos from 2024"
    folder.mkdir(parents=True)
    shutil.copy2(FIXTURES_DIR / "with-datetime-and-gps.jpg", folder / "IMG_001.jpg")
    sidecar = {
        "title": "IMG_001.jpg",
        "description": "",
        "photoTakenTime": {"timestamp": "1719935787"},  # 2024-07-02 15:56:27
        "geoData": {
            "latitude": 48.86,
            "longitude": 2.29,
            "altitude": 35,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        },
        "geoDataExif": {
            "latitude": 48.86,
            "longitude": 2.29,
            "altitude": 35,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        },
    }
    (folder / "IMG_001.jpg.supplemental-metadata.json").write_text(json.dumps(sidecar))


def _media_basename(lib: Path) -> str:
    """Return the GUID-named media file emitted by init (skips report.csv etc.)."""
    media_exts = {".jpg", ".jpeg", ".heic", ".png", ".mp4", ".mov", ".mp"}
    return next(
        f
        for f in os.listdir(lib)
        if not f.startswith(".") and os.path.splitext(f)[1].lower() in media_exts
    )


class TestAgentWorkflow:
    @patch("reverse_geocoder.search")
    @patch("pixelkasten.utils.clip.embed_images")
    def test_init_enrich_propose_apply_writes_proposed_album(self, mock_embed, mock_rg, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()
        _build_takeout_source(source)

        # 1. init -> working library
        ingest(
            make_options(source=str(source), destination=str(lib)),
            progress=noop_progress,
        )
        media_name = _media_basename(lib)

        # 2. enrich -> geocode + embed (mocked)
        mock_rg.return_value = [{"name": "Paris", "admin1": "IDF", "cc": "FR"}]
        mock_embed.return_value = np.full((1, 768), 0.1, dtype=np.float32)
        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            enrich(EnrichOptions(library=str(lib), video_frames=5))

        # Geocode result is now persisted in the sidecar
        sidecar_path = lib / ".pixelkasten" / f"{media_name}.pk.json"
        with open(sidecar_path) as f:
            sidecar = json.load(f)
        assert sidecar["location"]["name"] == "Paris, IDF, FR"

        # 3. propose -> agent's decision recorded
        propose(str(lib / media_name), "Paris weekend")
        with open(sidecar_path) as f:
            sidecar = json.load(f)
        assert sidecar["proposed_album"] == "Paris weekend"

        # 4. apply -> proposed_album drives the export folder
        run_export(str(lib), str(export), ExportOptions())

        files = []
        for dirpath, _dirs, fns in os.walk(str(export)):
            for f in fns:
                files.append(os.path.relpath(os.path.join(dirpath, f), str(export)))

        # File lands in the proposed album folder, prefixed with its date
        assert "2024/20240702-Paris weekend/20240702-155627.jpg" in files
