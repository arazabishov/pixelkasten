"""
Offline reverse geocoding — resolve GPS coordinates to location names.

Uses the reverse_geocoder library which bundles a local dataset (~30MB).
No API calls, no rate limits. Batch-resolves all unique coordinates in
a single call for efficiency.
"""

from pixelkasten.core.manifest import LocationInfo


def reverse_geocode(manifest: list[dict]) -> None:
    """
    Resolve GPS coordinates on manifest entries to location names.

    Reads GPS from entry["metadata"]["geo"] (set by reconcile) and writes:
        entry["location"]["name"]   — "San Francisco, California, US"
        entry["location"]["region"] — "California, US"

    Mutates entries in-place. Entries without GPS are skipped.
    Deduplicates coordinates (rounded to 2 decimals) so the geocoder
    is called once per unique location, not once per image.
    """
    import reverse_geocoder as rg

    # Collect unique coordinates → list of entries at each location.
    coord_to_entries: dict[tuple[float, float], list[dict]] = {}
    for entry in manifest:
        geo = entry.get("metadata", {}).get("geo")
        if not geo:
            continue
        lat, lon = geo.get("latitude"), geo.get("longitude")
        if lat is None or lon is None:
            continue
        rounded = (round(float(lat), 2), round(float(lon), 2))
        coord_to_entries.setdefault(rounded, []).append(entry)

    if not coord_to_entries:
        return

    # Batch resolve all unique coordinates in one call.
    coords_list = list(coord_to_entries.keys())
    results = rg.search(coords_list)

    for coord, result in zip(coords_list, results):
        city = result.get("name", "")
        region = result.get("admin1", "")
        country = result.get("cc", "")

        parts = [p for p in [city, region, country] if p]
        display_name = ", ".join(parts)
        region_display = ", ".join([p for p in [region, country] if p])

        location = LocationInfo(
            name=display_name,
            region=region_display,
            country=country,
        )

        for entry in coord_to_entries[coord]:
            entry["location"] = location
