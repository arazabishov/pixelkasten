"""
Agent-driven organization — Phase 4 of the AI pipeline.

Feeds cluster summaries (captions, EXIF dates, GPS locations, tags) to a
local text LLM via Ollama to propose a directory structure. The LLM never
sees image bytes — it works entirely with structured text, making it cheap
and leveraging what LLMs are best at: reasoning about categories and naming.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A text model pulled (`ollama pull qwen3.5:35b`)
"""

import json
from typing import Callable

import ollama as ollama_client


DEFAULT_MODEL = "qwen3.5:35b"


ORGANIZATION_PROMPT_TEMPLATE = """\
You are a photo organization assistant. Your job is to analyze clusters of \
similar photos and propose a directory structure for organizing them.

## Directory Naming Convention

Directories follow this exact format:
```
YYYY/YYYYMMDD - Event Name/
```

Examples:
- 2019/20190715 - Beach Vacation in Antalya/
- 2024/20240415 - Trip to Japan/
- 2023/20231225 - Christmas Dinner/

Rules:
- Year directory: 4 digits (YYYY)
- Event directory: YYYYMMDD (date of earliest photo), space, dash, space, descriptive name
- Event names should be concise but descriptive (2-5 words)
- Albums and loose files live directly under the year directory (no month subdirectories)
- If no date is available, use "Unknown/Descriptive Name" as the path

## Cluster Data

Here are the photo clusters to organize:

{cluster_summary}

## Instructions

For each cluster, propose a directory path following the naming convention above.

Reasoning guidelines:
- Use EXIF dates for the YYYYMMDD prefix when available
- Derive the event name from the captions, tags, and location data
- When a cluster spans multiple cities in the same region, use a broader geographic name \
that covers all cities (e.g., "Bay Area Trip" for San Francisco + Sunnyvale + Stanford, \
or "California Road Trip" if cities are spread across the state)
- When a cluster is in a single city, use that city name
- Name the album after the primary location — if most photos are in one region, use that \
region for the name even if a few photos are from elsewhere (transit, layovers)
- You MAY place multiple clusters under the same event directory if they clearly belong \
together (same date + location + topic)
- For clusters without dates, group by theme under Unknown/

Respond with ONLY a JSON object mapping cluster_id to directory path. \
No explanation, no markdown fences, no extra text. Example:

{{"7": "2019/20190715 - Beach Vacation in Antalya", \
"12": "2023/20231225 - Christmas Dinner"}}
"""


def build_cluster_summary_text(manifest: dict) -> str:
    """
    Build a text summary of all clusters for the LLM prompt.

    For each cluster, includes size, captions, tags, date range,
    GPS coordinates, and camera models (when available).

    Returns a formatted text block ready to embed in the LLM prompt.
    """
    clusters = manifest.get("clusters", {})
    if not clusters:
        return "(No clusters found in manifest.)"

    lines = []
    for cluster_id in sorted(clusters.keys(), key=lambda x: int(x)):
        cluster = clusters[cluster_id]
        size = cluster.get("size", 0)
        lines.append(f"Cluster {cluster_id} ({size} images):")

        # Captions from Phase 2.
        captions = cluster.get("captions", [])
        if captions:
            lines.append("  Captions:")
            for cap in captions:
                lines.append(f'    - "{cap}"')

        # Tags from Phase 1.
        tags = cluster.get("top_tags", [])
        if tags:
            lines.append(f"  Top tags: {', '.join(tags)}")

        # EXIF date range from Phase 3a.
        date_range = cluster.get("date_range")
        if date_range:
            lines.append(
                f"  Date range: {date_range['earliest']} to {date_range['latest']}"
            )

        # Location info: collect cities and regions, filtering out outliers.
        # If 90%+ of geotagged images are in one region, stray GPS from
        # transit or metadata errors gets ignored. This prevents "California
        # and Netherlands Travel" when 2 of 58 photos were taken mid-flight.
        from collections import Counter

        city_counts = Counter()
        region_counts = Counter()
        for entry in manifest["entries"]:
            if str(entry.get("cluster")) != cluster_id:
                continue
            exif = entry.get("exif", {})
            if exif.get("location_name"):
                city = exif["location_name"].split(",")[0].strip()
                city_counts[city] += 1
            if exif.get("location_region"):
                region_counts[exif["location_region"]] += 1

        # Filter: keep regions that represent >= 10% of geotagged images.
        total_geotagged = sum(region_counts.values())
        if total_geotagged > 0:
            significant_regions = [
                r for r, c in region_counts.items() if c / total_geotagged >= 0.1
            ]
            # Keep only cities belonging to significant regions.
            significant_cities = []
            for entry in manifest["entries"]:
                if str(entry.get("cluster")) != cluster_id:
                    continue
                exif = entry.get("exif", {})
                if exif.get("location_region") in significant_regions:
                    city = exif.get("location_name", "").split(",")[0].strip()
                    if city and city not in significant_cities:
                        significant_cities.append(city)

            if significant_cities:
                lines.append(f"  Cities: {', '.join(significant_cities)}")
            if significant_regions:
                lines.append(f"  Region: {', '.join(sorted(significant_regions))}")
        else:
            locations = cluster.get("locations", [])
            if locations:
                coords = [f"{loc['latitude']}, {loc['longitude']}" for loc in locations]
                lines.append(f"  GPS: {'; '.join(coords)}")

        # Cameras from Phase 3a.
        cameras = cluster.get("cameras", [])
        if cameras:
            lines.append(f"  Camera: {', '.join(str(c) for c in cameras)}")

        lines.append("")

    # Count noise images.
    n_noise = sum(
        1
        for e in manifest["entries"]
        if e.get("cluster") == -1 and e.get("status") == "ok"
    )
    if n_noise > 0:
        lines.append(f"Unclustered images ({n_noise} images):")
        lines.append(
            "  These did not fit into any cluster. They will go into Unsorted/."
        )

    return "\n".join(lines)


def build_organization_prompt(cluster_summary_text: str) -> str:
    """
    Build the full prompt for the LLM.

    Returns the prompt string with cluster data interpolated.
    """
    return ORGANIZATION_PROMPT_TEMPLATE.format(
        cluster_summary=cluster_summary_text,
    )


def propose_organization(
    manifest: dict,
    model: str = DEFAULT_MODEL,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """
    Send cluster summaries to the LLM and get back a directory structure proposal.

    Args:
        manifest: Parsed manifest dict (enriched with captions + EXIF).
        model: Ollama text model name.
        on_progress: Optional callback for status updates (text messages).

    Returns:
        Dict mapping cluster_id (string) to proposed directory path.
    """
    if on_progress:
        on_progress("Building cluster summaries...")

    summary_text = build_cluster_summary_text(manifest)
    prompt = build_organization_prompt(summary_text)

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

    raw_response = response.message.content.strip()

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
            raise ValueError(
                f"LLM did not return valid JSON. Raw response:\n{raw[:500]}"
            )
        result = json.loads(cleaned[start:end])

    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got: {type(result)}")

    # Ensure all keys and values are strings.
    return {str(k): str(v) for k, v in result.items()}
