"""Run the Headlyn pipeline's currently implemented stage."""

from __future__ import annotations

from pipeline import run_pipeline


def main() -> int:
    dataset = run_pipeline(split="test")
    print(f"dataset_loading: passed ({len(dataset.articles)} articles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
