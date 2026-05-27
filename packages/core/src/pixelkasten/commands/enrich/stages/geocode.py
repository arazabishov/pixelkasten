"""Reverse-geocode records with geo coordinates."""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.utils.record import read_record, write_record


def geocode(records: list[str], state: EnrichState, progress: Callable) -> None:
    """Reverse-geocode every record with geo set but no location yet."""
    pending, locations_already_set = _pending_geocodes(records)
    state.locations_already_set = locations_already_set

    if not pending:
        return

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
                state.locations_added += 1
                done += 1
                tick(done)


def _pending_geocodes(records: list[str]) -> tuple[dict[tuple[float, float], list[str]], int]:
    """Group records-needing-geocoding by rounded coordinate."""
    locations_already_set = 0
    pending: dict[tuple[float, float], list[str]] = {}
    for path in records:
        data = read_record(path)
        if data.get("location") is not None:
            locations_already_set += 1
        elif geo := data.get("geo"):
            lat, lon = round(geo["latitude"], 2), round(geo["longitude"], 2)
            pending.setdefault((lat, lon), []).append(path)
    return pending, locations_already_set


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
