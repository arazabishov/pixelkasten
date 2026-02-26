"""
Agent-driven organization — Phase 3b of the AI pipeline.

Feeds cluster summaries (captions, EXIF dates, GPS locations, tags) to a
local text LLM via Ollama to propose a directory structure. The LLM never
sees image bytes — it works entirely with structured text, making it cheap
and leveraging what LLMs are best at: reasoning about categories and naming.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A text model pulled (`ollama pull qwen3.5:35b`)
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
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
                lines.append(f"    - \"{cap}\"")

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
                r for r, c in region_counts.items()
                if c / total_geotagged >= 0.1
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
        1 for e in manifest["entries"]
        if e.get("cluster") == -1 and e.get("status") == "ok"
    )
    if n_noise > 0:
        lines.append(f"Unclustered images ({n_noise} images):")
        lines.append("  These did not fit into any cluster. They will go into Unsorted/.")

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


_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _date_directory_from_timestamp(timestamp: str) -> str | None:
    """
    Derive a YYYY/ directory path from an ISO 8601 timestamp.

    Loose files go directly under the year directory (no month subdirectory).
    Returns None if the timestamp can't be parsed.
    """
    if not timestamp:
        return None

    try:
        # Timestamps are like "2019-07-15T14:30:00" or with timezone.
        date_part = timestamp[:10]
        year, _month, _day = date_part.split("-")
        return year
    except (ValueError, IndexError):
        return None


def build_organization_plan(
    manifest: dict,
    cluster_directories: dict[str, str],
    noise_exif: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Convert the LLM's cluster->directory mapping into per-image source->target pairs.

    For each image in the manifest:
    - If it belongs to a cluster with a proposed directory, map it there.
    - If it's noise (cluster=-1) but has EXIF timestamp, place it in the
      date-based directory (YYYY/MM - Mon/) without an event subfolder.
    - Otherwise, put it in Unsorted/.
    - Preserve the original filename.

    Args:
        manifest: Parsed manifest dict.
        cluster_directories: The LLM's proposed mapping.
        noise_exif: Optional dict of image_path -> ExifData for noise images.
            Used to derive date directories for unclustered images.

    Returns:
        List of dicts with: source, target, cluster, reason.
    """
    noise_exif = noise_exif or {}

    plan = []
    for entry in manifest["entries"]:
        if entry.get("status") != "ok":
            continue

        source = entry["path"]
        filename = Path(source).name
        cluster_id = entry.get("cluster")
        cluster_key = str(cluster_id) if cluster_id is not None else None

        if cluster_key and cluster_key in cluster_directories:
            # Single-image clusters aren't useful as albums. Place them
            # in the bare month directory instead, like noise images.
            clusters = manifest.get("clusters", {})
            cluster_size = clusters.get(cluster_key, {}).get("size", 0)
            entry_exif = entry.get("exif")
            entry_ts = entry_exif.get("timestamp") if entry_exif else None

            if cluster_size == 1 and entry_ts:
                date_dir = _date_directory_from_timestamp(entry_ts)
                if date_dir:
                    plan.append({
                        "source": source,
                        "target": f"{date_dir}/{filename}",
                        "cluster": cluster_id,
                        "reason": "Single-image cluster, placed by date",
                    })
                    continue

            directory = cluster_directories[cluster_key]
            plan.append({
                "source": source,
                "target": f"{directory}/{filename}",
                "cluster": cluster_id,
                "reason": f"Cluster {cluster_key}: {Path(directory).name}",
            })
            continue

        # Noise/unmapped image: try to place by date if EXIF is available.
        # Check both the manifest entry's exif and the noise_exif lookup.
        timestamp = None
        entry_exif = entry.get("exif")
        if entry_exif and entry_exif.get("timestamp"):
            timestamp = entry_exif["timestamp"]
        elif source in noise_exif and noise_exif[source].get("timestamp"):
            timestamp = noise_exif[source]["timestamp"]

        date_dir = _date_directory_from_timestamp(timestamp) if timestamp else None

        if date_dir:
            plan.append({
                "source": source,
                "target": f"{date_dir}/{filename}",
                "cluster": cluster_id if cluster_id is not None else -1,
                "reason": f"Unclustered, placed by date ({timestamp[:10]})",
            })
        else:
            plan.append({
                "source": source,
                "target": f"Unsorted/{filename}",
                "cluster": cluster_id if cluster_id is not None else -1,
                "reason": "Unclustered, no date available",
            })

    return plan


def write_organization_plan(
    plan: list[dict],
    cluster_directories: dict[str, str],
    model: str,
    output_path: Path,
) -> None:
    """
    Write the organization plan to a JSON file for user review.

    No files are moved by this function. The output is meant to be
    inspected and optionally edited before any future apply step.
    """
    n_organized = sum(1 for p in plan if not p["target"].startswith("Unsorted/"))
    n_unsorted = sum(1 for p in plan if p["target"].startswith("Unsorted/"))

    output = {
        "version": 1,
        "model": model,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "total_images": len(plan),
        "organized": n_organized,
        "unsorted": n_unsorted,
        "cluster_directories": cluster_directories,
        "plan": plan,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)


def apply_organization_plan(
    plan_path: Path,
    destination: Path,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    """
    Execute an organization plan by copying files to the proposed structure.

    Reads organization.json, copies each source file to destination/target.
    Uses shutil.copy2 to preserve file metadata (timestamps, etc.).

    Args:
        plan_path: Path to organization.json.
        destination: Root directory to copy files into.
        on_progress: Optional callback, called with count of files processed.

    Returns:
        Dict with stats: {"copied": N, "skipped": N, "failed": N}
    """
    with open(plan_path) as f:
        organization = json.load(f)

    plan = organization["plan"]
    stats = {"copied": 0, "skipped": 0, "failed": 0}

    for i, entry in enumerate(plan):
        source = Path(entry["source"])
        target = destination / entry["target"]

        if not source.exists():
            stats["skipped"] += 1
        else:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                stats["copied"] += 1
            except Exception:
                stats["failed"] += 1

        if on_progress is not None:
            on_progress(i + 1)

    return stats


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
