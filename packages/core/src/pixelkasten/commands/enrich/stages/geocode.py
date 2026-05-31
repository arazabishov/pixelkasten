"""Reverse-geocode records with geo coordinates."""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichEntry, EnrichState


def geocode(state: EnrichState, progress: Callable) -> None:
    """Set `location` on the record of every entry that has geo coordinates.

    Stays pure with respect to disk: the location is written onto the held
    in-memory `Record`, and `emit` is still the only stage that persists it.
    Every run recomputes from scratch — there is no skip-if-already-set,
    matching ingest's "each run is a full run".
    """
    coordinates: list[tuple[float, float]] = []
    located: list[EnrichEntry] = []
    for entry in state.entries:
        if geo := entry.record.geo:
            coordinates.append((geo["latitude"], geo["longitude"]))
            located.append(entry)

    if not coordinates:
        return

    import reverse_geocoder as rg

    # One offline, batched search — a single vectorized k-d-tree query (the tree builds once
    # per process), so passing every coord is as cheap as deduping to unique ones first.
    results = rg.search(coordinates, verbose=False)

    with progress("Reverse geocoding", len(located)) as tick:
        for i, (entry, hit) in enumerate(zip(located, results)):
            entry.record.location = {
                "city": hit.get("name", ""),
                "region": hit.get("admin1", ""),
                "country": hit.get("cc", ""),
            }
            tick(i + 1)
