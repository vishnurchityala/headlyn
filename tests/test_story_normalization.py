from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from headlyn.story_normalization.llm import parse_entity_response
from headlyn.story_normalization.models import EntityExtraction, ExtractedEntity, StoryNormalizationConfig
from headlyn.story_normalization.pipeline import build_candidates, run_story_normalization


class FakeEntityExtractor:
    model_name = "fake-gemma4"

    def extract(self, item: dict[str, object]) -> EntityExtraction:
        title = str(item["title"])
        if "trade" in title.lower():
            entities = (
                ExtractedEntity("PM Modi", "Narendra Modi", "PERSON", "primary"),
                ExtractedEntity("India", "India", "GPE", "primary"),
            )
        elif "metro" in title.lower():
            entities = (
                ExtractedEntity("PM Modi", "Narendra Modi", "PERSON", "primary"),
                ExtractedEntity("Uttar Pradesh", "Uttar Pradesh", "GPE", "primary"),
            )
        else:
            entities = ()
        return EntityExtraction(
            article_id=str(item["article_id"]),
            input_fingerprint="fake",
            model=self.model_name,
            status="ok",
            entities=entities,
        )


class FakeLexicalScorer:
    model_name = "fake-bge-m3-sparse"

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        scores = []
        for left, right in pairs:
            scores.append(0.8 if "trade" in left.lower() and "trade" in right.lower() else 0.1)
        return scores


class StoryNormalizationTests(unittest.TestCase):
    def test_parse_entity_response_accepts_strict_json(self) -> None:
        entities = parse_entity_response(
            '{"entities":[{"text":"PM Modi","canonical_name":"Narendra Modi",'
            '"type":"PERSON","role":"primary"}]}'
        )
        self.assertEqual(entities[0].canonical_name, "Narendra Modi")
        self.assertEqual(entities[0].role, "primary")

    def test_generic_geography_does_not_create_a_candidate_pair(self) -> None:
        items = [
            make_item("article-a", "firstpost", "India headline A", "Description A"),
            make_item("article-b", "ndtv", "India headline B", "Description B"),
        ]
        extractions = {
            item["article_id"]: EntityExtraction(
                article_id=item["article_id"],
                input_fingerprint="fake",
                model="fake-gemma4",
                status="ok",
                entities=(ExtractedEntity("India", "India", "GPE", "primary"),),
            )
            for item in items
        }
        self.assertEqual(build_candidates(items, extractions, True), [])

    def test_groups_same_event_and_keeps_different_event_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            ingestion_dir = artifact_root / "rss_ingestion/test-run"
            sources = ("firstpost", "ndtv", "hindustan-times")
            items = {
                "firstpost": [
                    make_item(
                        "article-a",
                        "firstpost",
                        "PM Modi discusses India trade talks",
                        "PM Modi discussed the trade negotiations.",
                    ),
                    make_item(
                        "article-c",
                        "firstpost",
                        "PM Modi launches new metro project",
                        "The metro project was launched in Uttar Pradesh.",
                    ),
                ],
                "ndtv": [
                    make_item(
                        "article-b",
                        "ndtv",
                        "Narendra Modi speaks on India trade negotiations",
                        "Narendra Modi outlined India's trade position.",
                    )
                ],
                "hindustan-times": [
                    make_item(
                        "article-d",
                        "hindustan-times",
                        "Monsoon advances across Kerala",
                        "The monsoon advanced across Kerala on Thursday.",
                    )
                ],
            }
            for source_id, source_items in items.items():
                source_dir = ingestion_dir / source_id
                source_dir.mkdir(parents=True)
                (source_dir / "items.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in source_items)
                )
            (ingestion_dir / "summary.json").write_text(
                json.dumps({"sources": [{"source_id": source} for source in sources]})
            )

            result = run_story_normalization(
                StoryNormalizationConfig(
                    ingestion_run_id="test-run",
                    artifact_root=artifact_root,
                    merge_threshold=0.5,
                ),
                entity_extractor=FakeEntityExtractor(),
                lexical_scorer=FakeLexicalScorer(),
            )

            output_dir = artifact_root / "story_normalization/test-run"
            stories = [
                json.loads(line)
                for line in (output_dir / "stories.jsonl").read_text().splitlines()
            ]
            summary = json.loads((output_dir / "summary.json").read_text())
            self.assertEqual(result.status, "ok")
            self.assertEqual(len(stories), 3)
            self.assertEqual(summary["accepted_pair_count"], 1)
            self.assertEqual(summary["multi_source_story_count"], 1)
            trade_story = next(story for story in stories if story["article_count"] == 2)
            self.assertEqual(
                {article["article_id"] for article in trade_story["articles"]},
                {"article-a", "article-b"},
            )
            self.assertTrue((output_dir / "entity_extractions.jsonl").exists())
            self.assertTrue((output_dir / "pair_scores.jsonl").exists())
            debug_path = output_dir / "accepted_stories_debug.json"
            self.assertTrue(debug_path.exists())
            debug = json.loads(debug_path.read_text())
            self.assertEqual(debug["accepted_story_count"], 1)
            self.assertEqual(debug["article_count"], 2)
            self.assertEqual(len(debug["stories"][0]["accepted_pair_scores"]), 1)
            debug_article = debug["stories"][0]["articles"][0]
            self.assertIn("title", debug_article["content"])
            self.assertIn("description", debug_article["content"])
            self.assertIn("url", debug_article["details"])
            self.assertIn("entities", debug_article["entity_extraction"])
            self.assertTrue((output_dir / "newsletter_stories.json").exists())


def make_item(article_id: str, source_id: str, title: str, description: str) -> dict[str, object]:
    return {
        "article_id": article_id,
        "source_id": source_id,
        "source_name": source_id.title(),
        "title": title,
        "description": description,
        "published_at": "2026-05-28T10:00:00+00:00",
        "url": f"https://example.com/{article_id}",
    }


if __name__ == "__main__":
    unittest.main()
