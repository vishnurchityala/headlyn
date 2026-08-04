"""Manual status check for the dataset-loading stage."""

from __future__ import annotations

from pipeline import run_pipeline


def main() -> int:
    dataset = run_pipeline(split="test")
    print("dataset_loading: passed")
    print(f"split: {dataset.split}")
    print(f"articles: {len(dataset.articles)}")
    print(f"gold labels: {len(dataset.gold_labels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
