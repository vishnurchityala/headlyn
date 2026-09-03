from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any


EVALUATED_LABELS = {"same_story", "unrelated", "opposite"}


@dataclass(frozen=True)
class PairEvaluation:
    """Normalized result for one labelled article pair."""

    label: str
    predicted_same_story: bool


def load_json(path: Path) -> Any:
    """Load one UTF-8 JSON document from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_predictions(path: Path) -> tuple[dict[str, str], list[int]]:
    """Build a document-to-story map and collect predicted story sizes."""
    value = load_json(path)
    stories = value.get("stories", []) if isinstance(value, dict) else value
    if not isinstance(stories, list):
        raise ValueError("stories file must contain a stories list")

    assignments: dict[str, str] = {}
    sizes: list[int] = []
    for story in stories:
        if not isinstance(story, dict) or not story.get("story_id"):
            continue
        story_id = str(story["story_id"])
        members = story.get("articles", story.get("member_documents", []))
        if not isinstance(members, list):
            members = []
        member_count = 0
        for member in members:
            if not isinstance(member, dict):
                continue
            document_id = member.get("document_id", member.get("article_id"))
            if not document_id:
                continue
            assignments[str(document_id)] = story_id
            member_count += 1
        sizes.append(member_count)
    return assignments, sizes


def load_annotations(path: Path) -> list[dict[str, object]]:
    """Load and validate pair annotations from the phase dataset JSON file."""
    value = load_json(path)
    if not isinstance(value, list):
        raise ValueError("annotations file must contain a JSON list")
    annotations: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        required = {"article_id_a", "article_id_b", "label"}
        if required.issubset(item):
            annotations.append(item)
    return annotations


def evaluate_pairs(
    assignments: dict[str, str],
    annotations: list[dict[str, object]],
) -> tuple[dict[str, int], dict[str, dict[str, int]], list[PairEvaluation]]:
    """Compare predicted membership with labelled pairs and calculate confusion counts."""
    confusion = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}
    by_label: Counter[str] = Counter()
    label_correct: Counter[str] = Counter()
    evaluations: list[PairEvaluation] = []

    for annotation in annotations:
        label = str(annotation["label"])
        by_label[label] += 1
        if label not in EVALUATED_LABELS:
            continue
        article_a = str(annotation["article_id_a"])
        article_b = str(annotation["article_id_b"])
        if article_a not in assignments or article_b not in assignments:
            continue

        predicted_same = assignments[article_a] == assignments[article_b]
        expected_same = label == "same_story"
        evaluations.append(PairEvaluation(label, predicted_same))
        if predicted_same and expected_same:
            confusion["true_positive"] += 1
        elif predicted_same and not expected_same:
            confusion["false_positive"] += 1
        elif not predicted_same and expected_same:
            confusion["false_negative"] += 1
        else:
            confusion["true_negative"] += 1
        if predicted_same == expected_same:
            label_correct[label] += 1

    label_metrics = {
        label: {
            "count": by_label[label],
            "evaluated_count": sum(item.label == label for item in evaluations),
            "correct_count": label_correct[label],
        }
        for label in sorted(by_label)
    }
    return confusion, label_metrics, evaluations


def calculate_metrics(confusion: dict[str, int]) -> dict[str, float | int]:
    """Calculate binary pairwise precision, recall, F1, and accuracy."""
    true_positive = confusion["true_positive"]
    false_positive = confusion["false_positive"]
    true_negative = confusion["true_negative"]
    false_negative = confusion["false_negative"]
    precision = ratio(true_positive, true_positive + false_positive)
    recall = ratio(true_positive, true_positive + false_negative)
    f1 = ratio(2 * precision * recall, precision + recall)
    accuracy = ratio(true_positive + true_negative, sum(confusion.values()))
    return {
        **confusion,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def ratio(numerator: int | float, denominator: int | float) -> float:
    """Return a zero-safe ratio for sparse or incomplete annotation sets."""
    return float(numerator / denominator) if denominator else 0.0


def build_report(
    assignments: dict[str, str],
    story_sizes: list[int],
    annotations: list[dict[str, object]],
) -> dict[str, object]:
    """Build the complete clustering KPI report from persisted outputs."""
    confusion, by_label, evaluations = evaluate_pairs(assignments, annotations)
    evaluated_document_ids = {
        str(annotation[field])
        for annotation in annotations
        for field in ("article_id_a", "article_id_b")
        if field in annotation
    }
    missing_assignments = sum(
        1
        for annotation in annotations
        if str(annotation.get("article_id_a")) not in assignments
        or str(annotation.get("article_id_b")) not in assignments
    )
    return {
        "predicted_story_count": len(story_sizes),
        "assigned_document_count": len(assignments),
        "annotated_document_count": len(evaluated_document_ids),
        "singleton_story_count": sum(size == 1 for size in story_sizes),
        "largest_story_size": max(story_sizes, default=0),
        "average_story_size": mean(story_sizes) if story_sizes else 0.0,
        "median_story_size": median(story_sizes) if story_sizes else 0.0,
        "annotation_count": len(annotations),
        "evaluated_pair_count": len(evaluations),
        "missing_assignment_pair_count": missing_assignments,
        "skipped_pair_count": len(annotations) - len(evaluations) - missing_assignments,
        "label_counts": dict(Counter(str(item["label"]) for item in annotations)),
        "by_label": by_label,
        "pairwise_metrics": calculate_metrics(confusion),
    }


def print_report(report: dict[str, object]) -> None:
    """Print human-readable clustering KPIs to standard output."""
    print("Story Clustering Evaluation")
    print("===========================")
    print(f"Predicted stories: {report['predicted_story_count']}")
    print(f"Assigned documents: {report['assigned_document_count']}")
    print(f"Singleton stories: {report['singleton_story_count']}")
    print(f"Largest story: {report['largest_story_size']} documents")
    print(f"Average story size: {report['average_story_size']:.2f}")
    print(f"Median story size: {report['median_story_size']:.2f}")
    print()
    print("Pairwise evaluation")
    print("-------------------")
    print(f"Annotated pairs: {report['annotation_count']}")
    print(f"Evaluated pairs: {report['evaluated_pair_count']}")
    print(f"Missing-assignment pairs: {report['missing_assignment_pair_count']}")
    print(f"Skipped pairs: {report['skipped_pair_count']}")
    metrics = report["pairwise_metrics"]
    print()
    print("Strict pairwise metrics")
    print("-----------------------")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1:        {metrics['f1']:.4f}")
    print(f"Accuracy:  {metrics['accuracy']:.4f}")
    print()
    print("By label")
    print("--------")
    for label, values in report["by_label"].items():
        print(f"{label}: {values['evaluated_count']}/{values['count']} evaluated, {values['correct_count']} correct")


def parse_args() -> argparse.Namespace:
    """Parse clustering output, annotation dataset, and optional report paths."""
    parser = argparse.ArgumentParser(description="Evaluate generated story clusters against labelled pairs")
    parser.add_argument("--stories", type=Path, required=True, help="newsletter_stories.json generated by clustering")
    parser.add_argument("--annotations", type=Path, required=True, help="pair_annotations.json from the labelled dataset")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    return parser.parse_args()


def main() -> None:
    """Load clustering outputs, print KPIs, and optionally persist the report."""
    arguments = parse_args()
    assignments, story_sizes = load_predictions(arguments.stories)
    annotations = load_annotations(arguments.annotations)
    report = build_report(assignments, story_sizes, annotations)
    print_report(report)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote report: {arguments.output}")


if __name__ == "__main__":
    main()
