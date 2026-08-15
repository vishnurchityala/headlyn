from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from headlyn.newsletter.models import NewsletterConfig, StoryRewrite
from headlyn.newsletter.pipeline import run_newsletter
from headlyn.newsletter.rewrite import NewsletterRewriteError, parse_rewrite_response
from headlyn.newsletter.select import prepare_candidates, select_stories


class FakeRewriter:
    model_name = "fake-gemma"

    def rewrite(self, story: dict[str, object]) -> StoryRewrite:
        return StoryRewrite(
            story_id=str(story["story_id"]),
            headline=f"Rewritten: {story['representative_title']}",
            summary=f"Summary: {story['representative_description']}",
            section="National" if "india" in str(story["representative_title"]).lower() else "Other",
            status="ok",
            model=self.model_name,
            input_fingerprint="fake",
        )


class FailingRewriter(FakeRewriter):
    def rewrite(self, story: dict[str, object]) -> StoryRewrite:
        raise NewsletterRewriteError("test failure")


class FakeSender:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, edition: dict[str, object], html_body: str, text_body: str) -> int:
        self.calls += 1
        self.html_body = html_body
        self.text_body = text_body
        return 2


class NewsletterTests(unittest.TestCase):
    def test_parse_rewrite_response_enforces_sections(self) -> None:
        parsed = parse_rewrite_response(
            '{"headline":"Headline","summary":"A factual summary.","section":"National"}'
        )
        self.assertEqual(parsed["section"], "National")
        with self.assertRaises(NewsletterRewriteError):
            parse_rewrite_response(
                '{"headline":"Headline","summary":"Summary","section":"Politics & Sports"}'
            )

    def test_selection_prefers_publisher_diversity_and_caps_source(self) -> None:
        candidates = [
            candidate("story-1", "firstpost", "National", "2026-08-15T10:00:00+00:00"),
            candidate("story-2", "firstpost", "Politics", "2026-08-15T09:00:00+00:00"),
            candidate("story-3", "ndtv", "Business & Economy", "2026-08-15T08:00:00+00:00"),
            candidate("story-4", "indian-express", "Sports", "2026-08-15T07:00:00+00:00"),
            candidate("story-5", "hindustan-times", "World", "2026-08-15T06:00:00+00:00"),
            candidate("story-6", "firstpost", "Other", "2026-08-15T05:00:00+00:00"),
        ]
        selected, diagnostics = select_stories(candidates, target_items=5, max_items_per_source=2)
        self.assertEqual(len(selected), 5)
        self.assertEqual(diagnostics["selected_source_count"], 4)
        self.assertLessEqual(diagnostics["source_counts"]["firstpost"], 2)

    def test_preview_writes_newsletter_artifacts_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            story_dir = artifact_root / "story_normalization/run-1"
            story_dir.mkdir(parents=True)
            stories = [make_story(index) for index in range(6)]
            (story_dir / "newsletter_stories.json").write_text(
                json.dumps({"stories": stories}), encoding="utf-8"
            )
            result = run_newsletter(
                NewsletterConfig(
                    story_run_id="run-1",
                    edition_date="2026-08-15",
                    artifact_root=artifact_root,
                    minimum_items=5,
                    target_items=5,
                ),
                rewriter=FailingRewriter(),
            )
            output_dir = artifact_root / "daily_newsletter/2026-08-15"
            self.assertEqual(result.status, "preview")
            self.assertTrue((output_dir / "newsletter.html").exists())
            self.assertTrue((output_dir / "newsletter.txt").exists())
            self.assertTrue((output_dir / "selection.json").exists())
            summary = json.loads((output_dir / "summary.json").read_text())
            self.assertEqual(summary["rewrite_fallback_count"], 6)
            self.assertEqual(json.loads((output_dir / "delivery.json").read_text())["status"], "preview")
            html_output = (output_dir / "newsletter.html").read_text()
            self.assertIn("Read original", html_output)
            self.assertIn("Headlyn", html_output)
            self.assertIn("The Newsletter", html_output)
            self.assertIn('alt="Headlyn"', html_output)

    def test_held_edition_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            story_dir = artifact_root / "story_normalization/run-1"
            story_dir.mkdir(parents=True)
            (story_dir / "newsletter_stories.json").write_text(
                json.dumps({"stories": [make_story(1), make_story(2)]}), encoding="utf-8"
            )
            sender = FakeSender()
            result = run_newsletter(
                NewsletterConfig(
                    story_run_id="run-1",
                    edition_date="2026-08-15",
                    artifact_root=artifact_root,
                    minimum_items=5,
                    target_items=5,
                    send=True,
                ),
                rewriter=FakeRewriter(),
                sender=sender,
            )
            self.assertEqual(result.status, "held")
            self.assertEqual(sender.calls, 0)


def candidate(story_id: str, source_id: str, section: str, published_at: str) -> dict[str, object]:
    return {
        "story_id": story_id,
        "source_id": source_id,
        "source_name": source_id,
        "section": section,
        "headline": story_id,
        "summary": "summary",
        "published_at": published_at,
        "url": f"https://example.com/{story_id}",
        "article_count": 1,
        "source_count": 1,
        "confidence": None,
    }


def make_story(index: int) -> dict[str, object]:
    source_id = ("firstpost", "ndtv", "indian-express", "hindustan-times")[index % 4]
    title = f"India headline {index}"
    return {
        "story_id": f"story-{index}",
        "representative_article_id": f"article-{index}",
        "representative_title": title,
        "representative_description": f"Description for story {index}.",
        "latest_published_at": f"2026-08-15T{index + 1:02d}:00:00+00:00",
        "source_count": 1,
        "article_count": 1,
        "confidence": None,
        "articles": [
            {
                "article_id": f"article-{index}",
                "source_id": source_id,
                "source_name": source_id,
                "title": title,
                "description": f"Description for story {index}.",
                "published_at": f"2026-08-15T{index + 1:02d}:00:00+00:00",
                "url": f"https://example.com/article-{index}",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
