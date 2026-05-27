"""Reverse-geocode records with geo coordinates."""

from collections.abc import Callable
from dataclasses import dataclass

from pixelkasten.utils.record import read_record, record_paths, write_record


@dataclass
class GeocodeResult:
    """Counts produced by the geocode stage."""

    # total records walked across the working library
    records_total: int = 0

    # records that gained a `location` field this run
    locations_added: int = 0

    # records skipped because `location` was already set
    locations_already_set: int = 0


def geocode(library: str, progress: Callable) -> GeocodeResult:
    """Reverse-geocode every record with geo set but no location yet."""
    result = GeocodeResult()
    pending = _pending_geocodes(library, result)

    if not pending:
        return result

    import reverse_geocoder as rg

    coords = list(pending.keys())
    results = rg.search(coords, verbose=False)

    total = sum(len(v) for v in pending.values())
    with progress("Reverse geocoding", total) as tick:
        done = 0
        for coord, geocode_data in zip(coords, results):
            location = _format_location(geocode_data)
            for record_file in pending[coord]:
                data = read_record(record_file)
                data["location"] = location
                write_record(record_file, data)
                result.locations_added += 1
                done += 1
                tick(done)

    return result


def _pending_geocodes(library: str, result: GeocodeResult) -> dict[tuple[float, float], list[str]]:
    """Group records-needing-geocoding by rounded coordinate."""
    paths = record_paths(library)
    result.records_total = len(paths)

    pending: dict[tuple[float, float], list[str]] = {}
    for path in paths:
        data = read_record(path)
        if data.get("location") is not None:
            result.locations_already_set += 1
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
