"""
Zero-shot classification — assign human-readable labels to images.

# What is zero-shot classification?

Normally, to classify images you need labeled training data: thousands of
images tagged as "beach", "birthday", etc. A model learns the patterns
from these examples and can then classify new images.

Zero-shot classification skips the training entirely. Instead, it leverages
CLIP's ability to compare images and text in the same vector space:

1. Embed the text labels: "beach" → vector, "birthday" → vector, etc.
2. Embed the image → vector.
3. Compute cosine similarity between the image vector and each label vector.
4. The label with the highest similarity is the classification.

This works because CLIP was trained on 400M image-text pairs — it already
"knows" what a beach looks like relative to the word "beach". We're just
using that knowledge directly.

# Label sets

We define default label sets organized by category (scene, event, subject).
Users can customize these to match their photo library. The quality of
classification depends heavily on choosing labels that match the actual
content — adding "skiing" is only useful if you have ski photos.

Labels work best when they're specific but not too narrow:
- "beach" ✓ (specific, recognizable visual pattern)
- "sandy beach with palm trees" ✗ (too narrow, may miss rocky beaches)
- "outdoor" ✗ (too broad, will match everything outside)

# Prompt engineering

CLIP was trained on image-caption pairs where captions typically read like
"a photo of a dog" or "a picture of a sunset". Bare labels like "beach"
score lower than "a photo of a beach" because the latter is closer to what
CLIP saw during training. This is called "prompt engineering" — we wrap each
label in a template to match the training distribution. It's a well-known
technique that significantly improves zero-shot accuracy.
"""

import numpy as np

# Prompt template for zero-shot classification. Wrapping labels in "a photo
# of {label}" matches CLIP's training distribution and produces higher,
# more discriminative scores than bare label text.
PROMPT_TEMPLATE = "a photo of {label}"

# Default label sets, organized by category. Each category represents a
# different "axis" of classification. An image can score high in multiple
# categories simultaneously (e.g., "beach" scene + "travel" event).
DEFAULT_LABEL_SETS: dict[str, list[str]] = {
    "scene": [
        "beach",
        "mountain",
        "city street",
        "indoor room",
        "garden",
        "forest",
        "park",
        "restaurant",
        "lake or river",
        "snow",
    ],
    "event": [
        "birthday party",
        "wedding",
        "graduation",
        "holiday celebration",
        "concert",
        "travel or vacation",
        "sports",
        "dinner gathering",
    ],
    "subject": [
        "portrait of a person",
        "group photo of people",
        "landscape or scenery",
        "food or meal",
        "pet or animal",
        "document or text",
        "selfie",
        "architecture or building",
    ],
}


def classify(
    image_embeddings: np.ndarray,
    label_embeddings: np.ndarray,
    label_names: list[str],
    threshold: float = 0.2,
) -> list[list[tuple[str, float]]]:
    """
    Score images against a set of text labels using cosine similarity.

    For each image, returns the labels that score above the threshold,
    sorted by score (highest first). A score of 1.0 means perfect match;
    0.0 means completely unrelated.

    CLIP cosine similarity scores are typically low in absolute terms:
    strong matches score ~0.25-0.35, weak matches ~0.15-0.20. This is
    normal — the scores are relative (ranking matters, not the raw number).

    Args:
        image_embeddings: Shape (N, D) — one row per image.
        label_embeddings: Shape (M, D) — one row per text label.
        label_names: The text labels corresponding to each row in
            label_embeddings. Must have length M.
        threshold: Minimum cosine similarity to include a label. Labels
            scoring below this are considered irrelevant for the image.

    Returns:
        A list of length N, where each element is a list of (label, score)
        tuples sorted by descending score. Only labels above the threshold
        are included.
    """
    # Matrix multiplication of (N, D) @ (D, M) = (N, M).
    # Each cell [i, j] is the cosine similarity between image i and label j.
    # This works because both embeddings are L2-normalized (see embed.py).
    scores = image_embeddings @ label_embeddings.T

    results = []
    for i in range(len(image_embeddings)):
        tags = []
        for j, name in enumerate(label_names):
            score = float(scores[i, j])
            if score >= threshold:
                tags.append((name, score))

        # Sort by score descending — most relevant label first.
        tags.sort(key=lambda x: x[1], reverse=True)
        results.append(tags)

    return results


def build_label_list(
    label_sets: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Flatten label sets into a single list with category prefixes.

    Each label gets a category prefix so you can trace which set it came
    from when reading the manifest.

    Args:
        label_sets: Dict of category → labels. Uses DEFAULT_LABEL_SETS
            if not provided.

    Returns:
        A tuple of (prefixed_names, prompted_labels):
        - prefixed_names: ["scene:beach", "scene:mountain", ...] for manifest.
        - prompted_labels: ["a photo of beach", "a photo of mountain", ...]
          for embedding. The prompt template improves CLIP's zero-shot accuracy
          (see module docstring).
    """
    if label_sets is None:
        label_sets = DEFAULT_LABEL_SETS

    prefixed_names = []
    prompted_labels = []

    for category, labels in label_sets.items():
        for label in labels:
            prefixed_names.append(f"{category}:{label}")
            prompted_labels.append(PROMPT_TEMPLATE.format(label=label))

    return prefixed_names, prompted_labels
