"""Rewrite NHTSA complaints into Hinglish for symptom-classifier training.

Standalone script; never imported by the web app.

Usage (from the repo root):
    python backend/scripts/augment_nhtsa.py complaints.csv -o augmented.csv
    python backend/scripts/augment_nhtsa.py complaints.csv --dry-run
"""
import argparse
import csv
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

# Make ``app`` importable when run as ``python backend/scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

TEXT_COLUMNS = ("complaint_text", "text", "description", "complaint")
COMPONENT_COLUMNS = ("component", "COMPONENT", "system", "category")
MIN_COSINE = 0.78


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _tfidf_cosine(first: str, second: str) -> float:
    """Small dependency-free TF-IDF cosine similarity for two documents."""
    first_tokens = _tokens(first)
    second_tokens = _tokens(second)
    if not first_tokens or not second_tokens:
        return 0.0
    first_counts = Counter(first_tokens)
    second_counts = Counter(second_tokens)
    vocabulary = set(first_counts) | set(second_counts)
    document_frequency = {
        term: int(term in first_counts) + int(term in second_counts)
        for term in vocabulary
    }

    def weight(count: int, frequency: int) -> float:
        return (1.0 + math.log(count)) * (math.log(3.0 / (1.0 + frequency)) + 1.0)

    first_vector = {
        term: weight(first_counts[term], document_frequency[term])
        for term in first_counts
    }
    second_vector = {
        term: weight(second_counts[term], document_frequency[term])
        for term in second_counts
    }
    dot = sum(value * second_vector.get(term, 0.0) for term, value in first_vector.items())
    first_norm = math.sqrt(sum(value * value for value in first_vector.values()))
    second_norm = math.sqrt(sum(value * value for value in second_vector.values()))
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0
    return dot / (first_norm * second_norm)


def _rewrite_hinglish(client, text: str) -> str:
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You rewrite US NHTSA car complaints into natural Hinglish for "
                    "Indian drivers. Preserve the technical meaning, symptoms, "
                    "components, and any numbers. Do not add advice, prices, or "
                    "invented details. Return only the rewritten complaint."
                ),
            },
            {"role": "user", "content": text[:4000]},
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return (response.choices[0].message.content or "").strip()


def _field(fieldnames, candidates) -> str | None:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input NHTSA CSV")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("augmented_nhtsa.csv"),
        help="Output CSV (default: augmented_nhtsa.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only the first 5 rows as a smoke test",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to process")
    args = parser.parse_args()

    if not settings.GROQ_API_KEY:
        print("GROQ_API_KEY is required for dataset augmentation.", file=sys.stderr)
        return 2
    if not args.input.is_file():
        print(f"Input CSV not found: {args.input}", file=sys.stderr)
        return 2

    try:
        from groq import Groq
    except ImportError:
        print("The groq package is required (pip install groq).", file=sys.stderr)
        return 2

    with args.input.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        text_column = _field(fieldnames, TEXT_COLUMNS) or (fieldnames[0] if fieldnames else None)
        component_column = _field(fieldnames, COMPONENT_COLUMNS)
        if text_column is None:
            print("Input CSV has no text column.", file=sys.stderr)
            return 2
        rows = list(reader)

    limit = 5 if args.dry_run else args.limit
    if limit is not None:
        rows = rows[: max(0, limit)]

    client = Groq(
        api_key=settings.GROQ_API_KEY,
        timeout=settings.GROQ_TIMEOUT_S,
    )
    accepted = 0
    skipped = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=["original_text", "hinglish_text", "component", "cosine_sim"],
        )
        writer.writeheader()
        for index, row in enumerate(rows):
            original = (row.get(text_column) or "").strip()
            if not original:
                skipped += 1
                continue
            try:
                hinglish = _rewrite_hinglish(client, original)
            except Exception as exc:
                print(
                    f"Row {index + 1} skipped: Groq {type(exc).__name__}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            similarity = _tfidf_cosine(original, hinglish)
            if similarity < MIN_COSINE or not hinglish:
                skipped += 1
            else:
                writer.writerow(
                    {
                        "original_text": original,
                        "hinglish_text": hinglish,
                        "component": (row.get(component_column) or "") if component_column else "",
                        "cosine_sim": f"{similarity:.4f}",
                    }
                )
                accepted += 1
            if index < len(rows) - 1:
                time.sleep(2.0)  # 1 request / 2 seconds

    print(f"Accepted {accepted} rows, skipped {skipped}. Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
