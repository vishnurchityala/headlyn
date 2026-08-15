from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from headlyn.ingestion.models import PipelineConfig
from headlyn.ingestion.normalize import normalize_title, normalize_url
from headlyn.ingestion.parse import parse_rss
from headlyn.ingestion.registry import available_sources, get_feed
from headlyn.ingestion.pipeline import run_pipeline


ROOT_DIR = Path(__file__).resolve().parents[1]


class IngestionContractTests(unittest.TestCase):
    def test_registered_sources(self) -> None:
        self.assertEqual(
            available_sources(),
            ("firstpost", "indian-express", "ndtv", "hindustan-times"),
        )
        self.assertEqual(get_feed("firstpost").scope, "india-general")
        self.assertEqual(get_feed("indian-express").feed_url, "https://indianexpress.com/section/india/feed/")
        self.assertEqual(get_feed("ndtv").feed_url, "https://feeds.feedburner.com/ndtvnews-india-news")
        self.assertEqual(
            get_feed("hindustan-times").feed_url,
            "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
        )

    def test_normalize_url_removes_tracking_and_fragment(self) -> None:
        self.assertEqual(
            normalize_url(
                "https://Example.com/story?utm_source=x&b=2&fbclid=abc#publisher=newsstand"
            ),
            "https://example.com/story?b=2",
        )

    def test_normalize_title_collapses_punctuation(self) -> None:
        self.assertEqual(normalize_title("  A headline: with HTML! "), "a headline with html")

    def test_parse_rss_snapshot(self) -> None:
        path = ROOT_DIR / "assets/rss-feeds/raw/2026-05-28/firstpost/feed.xml"
        entries = parse_rss(path.read_bytes())
        self.assertGreater(len(entries), 0)
        self.assertTrue(entries[0].title)
        self.assertTrue(entries[0].description)
        self.assertTrue(entries[0].published_at.endswith("+00:00"))

    def test_parse_rss_content_encoded_fallback(self) -> None:
        payload = b"""<?xml version='1.0'?>
        <rss xmlns:content='http://purl.org/rss/1.0/modules/content/'>
          <channel><item>
            <guid>https://example.com/story</guid>
            <title><![CDATA[Example title]]></title>
            <content:encoded><![CDATA[<p>Encoded description.</p>]]></content:encoded>
            <pubDate>Thu, 16 Jul 2026 21:17:21 +0530</pubDate>
          </item></channel>
        </rss>"""
        entries = parse_rss(payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].description, "Encoded description.")
        self.assertEqual(entries[0].url, "https://example.com/story")

    def test_parse_rss_uses_title_when_description_is_missing(self) -> None:
        payload = b"""<?xml version='1.0'?>
        <rss><channel><item>
          <guid>https://example.com/story</guid>
          <title>Title-only story</title>
          <pubDate>Thu, 16 Jul 2026 21:17:21 +0530</pubDate>
        </item></channel></rss>"""
        entries = parse_rss(payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].description, "Title-only story")

    def test_pipeline_writes_source_scoped_snapshot_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_pipeline(
                PipelineConfig(
                    mode="snapshot",
                    snapshot_date="2026-05-28",
                    run_id="test-run",
                    artifact_root=Path(directory),
                    source_ids=("firstpost", "ndtv", "hindustan-times"),
                    limit=3,
                    max_workers=3,
                )
            )
            output_dir = Path(directory) / "rss_ingestion/test-run"
            self.assertEqual(result.status, "ok")
            self.assertEqual(len(result.source_results), 3)
            self.assertTrue((output_dir / "summary.json").exists())
            for source_id in ("firstpost", "ndtv", "hindustan-times"):
                source_dir = output_dir / source_id
                self.assertTrue((source_dir / "feed.xml").exists())
                self.assertTrue((source_dir / "items.jsonl").exists())
                self.assertTrue((source_dir / "summary.json").exists())
                items = [
                    json.loads(line)
                    for line in (source_dir / "items.jsonl").read_text().splitlines()
                ]
                self.assertEqual(len(items), 3)
                self.assertTrue(all(item["source_id"] == source_id for item in items))

    def test_pipeline_isolates_a_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_pipeline(
                PipelineConfig(
                    mode="snapshot",
                    snapshot_date="2026-05-28",
                    run_id="partial-run",
                    artifact_root=Path(directory),
                    source_ids=("firstpost", "indian-express"),
                    limit=2,
                    max_workers=2,
                )
            )
            self.assertEqual(result.status, "partial")
            by_source = {source.source_id: source for source in result.source_results}
            self.assertEqual(by_source["firstpost"].status, "ok")
            self.assertEqual(by_source["indian-express"].status, "failed")
            self.assertTrue(
                (Path(directory) / "rss_ingestion/partial-run/indian-express/summary.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
