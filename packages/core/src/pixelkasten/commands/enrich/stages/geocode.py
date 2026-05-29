"""Reverse-geocode records with geo coordinates."""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichEntry, EnrichState
from pixelkasten.utils.record import read_record


def geocode(state: EnrichState, progress: Callable) -> None:
    """Record a `location` on every entry whose record has geo coordinates.

    Pure stage: results are stashed on `entry.location` and `emit` persists
    them. Every run recomputes from scratch — there is no skip-if-already-set,
    matching ingest's "each run is a full run".
    """
    located: list[EnrichEntry] = []
    coordinates: list[tuple[float, float]] = []
    for entry in state.entries:
        data = read_record(entry.record)
        if geo := data.get("geo"):
            located.append(entry)
            coordinates.append((geo["latitude"], geo["longitude"]))

    if not coordinates:
        return

    import reverse_geocoder as rg

    # One offline, batched search — a single vectorized k-d-tree query (the tree builds once
    # per process), so passing every coord is as cheap as deduping to unique ones first.
    results = rg.search(coordinates, verbose=False)

    with progress("Reverse geocoding", len(located)) as tick:
        for i, (entry, hit) in enumerate(zip(located, results)):
            entry.location = {
                "city": hit.get("name", ""),
                "region": hit.get("admin1", ""),
                "country": hit.get("cc", ""),
            }
            tick(i + 1)
