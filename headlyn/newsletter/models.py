from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SECTION_ORDER = (
    "National",
    "Politics",
    "Business & Economy",
    "Technology & Science",
    "World",
    "Sports",
    "Other",
)


@dataclass(frozen=True)
class NewsletterConfig:
    story_run_id: str
    edition_date: str
    artifact_root: Path | None = None
    llm_model: str = "gemma4:e4b-it-q4_K_M"
    llm_endpoint: str = "http://127.0.0.1:11434/api/generate"
    llm_timeout_seconds: int = 120
    target_items: int = 10
    minimum_items: int = 5
    max_items_per_source: int = 3
    unsubscribe_instructions: str | None = None
    send: bool = False
    force_rebuild: bool = False
    force_resend: bool = False


@dataclass(frozen=True)
class StoryRewrite:
    story_id: str
    headline: str
    summary: str
    section: str
    status: str
    model: str
    input_fingerprint: str
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "story_id": self.story_id,
            "headline": self.headline,
            "summary": self.summary,
            "section": self.section,
            "status": self.status,
            "model": self.model,
            "input_fingerprint": self.input_fingerprint,
            "error": self.error,
        }


@dataclass(frozen=True)
class NewsletterResult:
    edition_date: str
    story_run_id: str
    status: str
    selected_story_count: int
    output_dir: Path
    summary_path: Path
