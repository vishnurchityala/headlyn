from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

# Allow the script to be run directly from the repository root.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from headlyn.story_clustering.models import THRESHOLD_BINS, PreparedDocument, StoryClusteringConfig
from headlyn.story_clustering.pipeline import run_story_clustering
from headlyn.story_clustering.preparation import prepared_document_from_dict
from headlyn.story_index.config import StoryIndexConfig
from headlyn.story_index.hybrid_index import HybridStoryIndex
from headlyn.story_index.qdrant_store import QdrantStoryStore
from headlyn.story_index.sqlite_store import SQLiteStoryStore

from scripts.evaluate_story_clusters import build_report, load_annotations, load_predictions


def load_prepared_documents(path: Path) -> list[PreparedDocument]:
    """Load validated document features once for all threshold runs."""
    if not path.exists():
        raise FileNotFoundError(f"prepared feature file not found: {path}")
    return [
        prepared_document_from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_threshold(
    threshold: float,
    *,
    documents: list[PreparedDocument],
    artifact_root: Path,
    annotations_path: Path,
) -> dict[str, object]:
    """Run clustering with one threshold on a fresh story index."""
    configured = StoryIndexConfig.from_env()
    run_id = f"phase0-threshold-{threshold:.2f}"
    index_config = StoryIndexConfig(
        qdrant_url=configured.qdrant_url,
        qdrant_api_key=configured.qdrant_api_key,
        qdrant_collection=f"{configured.qdrant_collection}-threshold-{threshold:.2f}-{uuid.uuid4().hex[:8]}",
        qdrant_timeout_seconds=configured.qdrant_timeout_seconds,
        sqlite_path=artifact_root / f"{run_id}.sqlite3",
        vector_size=configured.vector_size,
        document_embedding_collection=configured.document_embedding_collection,
        document_embedding_vector_size=configured.document_embedding_vector_size,
        dense_limit=configured.dense_limit,
        lexical_limit=configured.lexical_limit,
    )
    state = SQLiteStoryStore(index_config.sqlite_path)
    index = HybridStoryIndex(
        index_config,
        dense_store=QdrantStoryStore(index_config),
        state_store=state,
    )
    try:
        result = run_story_clustering(
            StoryClusteringConfig(
                run_id=run_id,
                artifact_root=artifact_root,
                match_threshold=threshold,
            ),
            documents=documents,
            index=index,
        )
    finally:
        state.close()

    stories_path = result.output_dir / "newsletter_stories.json"
    assignments, story_sizes = load_predictions(stories_path)
    annotations = load_annotations(annotations_path)
    report = build_report(assignments, story_sizes, annotations)
    report["threshold"] = threshold
    report["story_run_id"] = run_id
    report["assignment_summary"] = json.loads(result.summary_path.read_text(encoding="utf-8"))
    return report


def parse_args() -> argparse.Namespace:
    """Parse prepared features, labels, and output locations."""
    parser = argparse.ArgumentParser(description="Run story clustering threshold calibration")
    parser.add_argument("--features", type=Path, required=True, help="document_features.jsonl from preparation")
    parser.add_argument("--annotations", type=Path, required=True, help="labelled pair annotations JSON")
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts/stages"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluations/threshold-sweep.json"))
    return parser.parse_args()


def main() -> None:
    """Run all configured threshold bins and write a comparison report."""
    arguments = parse_args()
    documents = load_prepared_documents(arguments.features)
    reports = [
        run_threshold(
            threshold,
            documents=documents,
            artifact_root=arguments.artifact_root,
            annotations_path=arguments.annotations,
        )
        for threshold in THRESHOLD_BINS
    ]
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps({"thresholds": reports}, indent=2) + "\n", encoding="utf-8")
    print("Threshold  Precision  Recall  F1      False merges  Missed same-story")
    for report in reports:
        metrics = report["pairwise_metrics"]
        print(
            f"{report['threshold']:.2f}       "
            f"{metrics['precision']:.4f}    "
            f"{metrics['recall']:.4f}  "
            f"{metrics['f1']:.4f}  "
            f"{metrics['false_positive']:12d}  "
            f"{metrics['false_negative']:17d}"
        )
    print(f"Wrote report: {arguments.output}")


if __name__ == "__main__":
    main()
