"""
LLM-powered album naming for photo clusters.

Feeds cluster summaries (captions, EXIF dates, GPS locations, tags) to a
local text LLM via Ollama to propose album names. The LLM never sees image
bytes — it works entirely with structured text, making it cheap and leveraging
what LLMs are best at: reasoning about categories and naming.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A text model pulled (`ollama pull qwen3.5:35b`)
"""

import json
from collections import Counter
from typing import Callable

import ollama as ollama_client

from pixelkasten.configuration import DiscoveryOptions

DEFAULT_MODEL = "qwen3.5:35b"


PROMPT_TEMPLATE = """\
You are a photo organization assistant. Your job is to analyze clusters of \
similar photos and propose a descriptive album name for each cluster.

## Album Naming Guidelines

- Album names should be concise but descriptive (2-5 words)
- Derive the name from the captions, tags, and location data
- When a cluster spans multiple cities in the same region, use a broader \
geographic name (e.g., "Bay Area Trip" for San Francisco + Sunnyvale, \
or "California Road Trip" if cities are spread across the state)
- When a cluster is in a single city, include that city name
- Name the album after the primary location — if most photos are in one \
region, use that region even if a few photos are from elsewhere

## Cluster Data

{cluster_summary}

## Instructions

For each cluster, propose a descriptive album name.

Respond with ONLY a JSON object mapping cluster_id to album name. \
No explanation, no markdown fences, no extra text. Example:

{{"7": "Beach Vacation in Antalya", "12": "Christmas Dinner"}}
"""


def build_cluster_summary_text(manifest: dict) -> str:
    """
    Build a text summary of all clusters for the LLM prompt.

    Aggregates captions, tags, date ranges, and locations from entries.

    Returns a formatted text block ready to embed in the LLM prompt.
    """
    clusters = manifest.get("clusters", {})
    if not clusters:
        return "(No clusters found in manifest.)"

    entries = manifest.get("entries", [])

    # Group entries by cluster for efficient single-pass aggregation.
    entries_by_cluster: dict[str, list] = {}
    for entry in entries:
        if not entry.discovery:
            continue
        cid = str(entry.discovery.cluster if entry.discovery.cluster is not None else -1)
        if cid in clusters:
            entries_by_cluster.setdefault(cid, []).append(entry)

    lines = []
    for cluster_id in sorted(clusters.keys(), key=lambda x: int(x)):
        cluster = clusters[cluster_id]
        size = cluster.get("size", 0)
        lines.append(f"Cluster {cluster_id} ({size} images):")

        cluster_entries = entries_by_cluster.get(cluster_id, [])

        # Captions from representative images.
        captions = [
            entry.discovery.caption
            for entry in cluster_entries
            if entry.discovery and entry.discovery.caption
        ]
        if captions:
            lines.append("  Captions:")
            for cap in captions:
                lines.append(f'    - "{cap}"')

        # Tags aggregated from all entries in the cluster.
        tag_counts: Counter = Counter()
        for entry in cluster_entries:
            if entry.discovery:
                for tag in entry.discovery.tags:
                    tag_counts[tag.name] += 1
        if tag_counts:
            top_tags = [name for name, _ in tag_counts.most_common(5)]
            lines.append(f"  Top tags: {', '.join(top_tags)}")

        # Date range from metadata timestamps (populated by reconcile).
        timestamps = []
        for entry in cluster_entries:
            dates = entry.metadata.dates if entry.metadata else []
            if dates:
                timestamps.append(dates[0])
        if timestamps:
            timestamps.sort()
            lines.append(f"  Date range: {timestamps[0]} to {timestamps[-1]}")

        # Location info: collect cities and regions, filtering out outliers.
        # If 90%+ of geotagged images are in one region, stray GPS from
        # transit or metadata errors gets ignored.
        city_counts: Counter = Counter()
        region_counts: Counter = Counter()
        for entry in cluster_entries:
            if not entry.location:
                continue
            if entry.location.name:
                city = entry.location.name.split(",")[0].strip()
                city_counts[city] += 1
            if entry.location.region:
                region_counts[entry.location.region] += 1

        total_geotagged = sum(region_counts.values())
        if total_geotagged > 0:
            significant_regions = [
                r for r, c in region_counts.items() if c / total_geotagged >= 0.1
            ]
            significant_cities = []
            for entry in cluster_entries:
                if not entry.location:
                    continue
                if entry.location.region in significant_regions:
                    city = entry.location.name.split(",")[0].strip() if entry.location.name else ""
                    if city and city not in significant_cities:
                        significant_cities.append(city)

            if significant_cities:
                lines.append(f"  Cities: {', '.join(significant_cities)}")
            if significant_regions:
                lines.append(f"  Region: {', '.join(sorted(significant_regions))}")

        lines.append("")

    return "\n".join(lines)


def propose_albums(manifest: dict, options: DiscoveryOptions) -> None:
    """
    Call LLM to propose album names, then mutate manifest entries.

    For each cluster that the LLM names, sets
    entry["source"] = {"type": "album", "name": name}.

    Entries not in any cluster (noise, cluster=-1) or in clusters the LLM
    didn't name are left as-is (typically source.type = "loose").

    Args:
        manifest: Manifest dict with "entries" list and "clusters" dict.
        options: Dict with optional "model" key for Ollama model name.
    """
    album_names = _propose_organization(manifest, model=options.organize_model)

    from pixelkasten.manifest import Source

    for entry in manifest.get("entries", []):
        if not entry.discovery:
            continue
        cluster_id = str(entry.discovery.cluster if entry.discovery.cluster is not None else -1)

        if cluster_id not in album_names or cluster_id == "-1":
            continue

        name = album_names[cluster_id]
        if name:
            entry.source = Source(type="album", name=name)


def _propose_organization(
    manifest: dict,
    model: str = DEFAULT_MODEL,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """
    Send cluster summaries to the LLM and get back album name proposals.

    Args:
        manifest: Manifest dict with entries and clusters.
        model: Ollama text model name.
        on_progress: Optional callback for status updates.

    Returns:
        Dict mapping cluster_id (string) to proposed album name.
    """
    if on_progress:
        on_progress("Building cluster summaries...")

    summary_text = build_cluster_summary_text(manifest)
    prompt = PROMPT_TEMPLATE.format(cluster_summary=summary_text)

    if on_progress:
        on_progress("Sending to LLM...")

    response = ollama_client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    content = response.message.content
    raw_response = content.strip() if content else ""

    if on_progress:
        on_progress("Parsing response...")

    return _parse_llm_response(raw_response)


def _parse_llm_response(raw: str) -> dict[str, str]:
    """
    Parse the LLM's JSON response, handling common formatting issues.

    The model may wrap in markdown fences or add explanatory text.
    """
    cleaned = raw.strip()

    # Strip markdown fences if present.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try direct parse first.
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: find the first { ... } block.
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"LLM did not return valid JSON. Raw response:\n{raw[:500]}")
        result = json.loads(cleaned[start:end])

    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got: {type(result)}")

    # Ensure all keys and values are strings.
    return {str(k): str(v) for k, v in result.items()}
