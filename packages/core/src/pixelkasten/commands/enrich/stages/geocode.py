"""Reverse-geocode records with geo coordinates."""

from collections.abc import Callable
from typing import Protocol

from pixelkasten.utils.record import read_record, record_paths, write_record


class GeocodeSummary(Protocol):
    records_total: int
    locations_added: int
    locations_already_set: int


def geocode(library: str, summary: GeocodeSummary, progress: Callable) -> None:
    """Reverse-geocode every record with geo set but no location yet."""
    pending = _pending_geocodes(library, summary)

    if not pending:
        return

    import reverse_geocoder as rg

    coords = list(pending.keys())
    results = rg.search(coords, verbose=False)

    total = sum(len(v) for v in pending.values())
    with progress("Reverse geocoding", total) as tick:
        done = 0
        for coord, result in zip(coords, results):
            location = _format_location(result)
            for record_file in pending[coord]:
                data = read_record(record_file)
                data["location"] = location
                write_record(record_file, data)
                summary.locations_added += 1
                done += 1
                tick(done)


def _pending_geocodes(
    library: str, summary: GeocodeSummary
) -> dict[tuple[float, float], list[str]]:
    """Group records-needing-geocoding by rounded coordinate."""
    paths = record_paths(library)
    summary.records_total = len(paths)

    pending: dict[tuple[float, float], list[str]] = {}
    for path in paths:
        data = read_record(path)
        if data.get("location") is not None:
            summary.locations_already_set += 1
        elif geo := data.get("geo"):
            lat, lon = round(geo["latitude"], 2), round(geo["longitude"], 2)
            pending.setdefault((lat, lon), []).append(path)
    return pending


def _format_location(rg_result: dict) -> dict:
    """Shape one reverse_geocoder hit into the record's ``location`` field."""
    city = rg_result.get("name", "")
    region = rg_result.get("admin1", "")
    country = rg_result.get("cc", "")
    parts = [p for p in [city, region, country] if p]
    return {
        "name": ", ".join(parts),
        "region": ", ".join([p for p in [region, country] if p]),
        "country": country,
    }
