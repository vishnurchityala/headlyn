from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from headlyn.document_processing.adapters import RssArticleAdapter, VideoDocumentAdapter
from headlyn.document_processing.canonical import build_canonical_text, document_fingerprint
from headlyn.document_processing.entities import parse_entity_response
from headlyn.document_processing.models import (
    DocumentPreparationConfig,
    EncodedDocument,
    EntityExtraction,
    ExtractedEntity,
)
from headlyn.document_processing.pipeline import load_documents, run_document_preparation


class FakeEncoder:
    model_name = "fake-bge-m3"

    def encode(self, documents):
        return [
            EncodedDocument(
                document_id=document.document_id,
                input_fingerprint=document_fingerprint(document),
                canonical_text=build_canonical_text(document),
                dense_vector=(1.0, 0.0),
                sparse_weights={"1": 0.5},
                model_name=self.model_name,
                max_length=512,
            )
            for document in documents
        ]


class FakeExtractor:
    model_name = "fake-gemma"
    prompt_version = "fake-v1"

    def extract(self, document):
        return EntityExtraction(
            document_id=document.document_id,
            input_fingerprint=document_fingerprint(document),
            model=self.model_name,
            prompt_version=self.prompt_version,
            status="ok",
            entities=(ExtractedEntity("India", "India", "GPE", "secondary"),),
        )


class FailingExtractor(FakeExtractor):
    def extract(self, document):
        raise RuntimeError("extractor unavailable")


class DocumentProcessingTests(unittest.TestCase):
    def test_rss_and_video_adapters_share_document_contract(self):
        article = RssArticleAdapter().adapt(article_value())
        video = VideoDocumentAdapter().adapt(video_value())
        self.assertEqual(article.document_type, "article")
        self.assertEqual(video.document_type, "video")
        self.assertEqual(article.body_text, "Description")
        self.assertEqual(video.body_text, "Transcript summary")

    def test_video_requires_summary(self):
        value = video_value()
        value.pop("summary")
        with self.assertRaisesRegex(ValueError, "summary is required"):
            VideoDocumentAdapter().adapt(value)

    def test_canonical_text_strips_html_and_is_fingerprintable(self):
        document = RssArticleAdapter().adapt(
            {**article_value(), "description": "<p>India &amp; trade</p>"}
        )
        self.assertEqual(
            build_canonical_text(document),
            "Title: Headline\n\nContent: India & trade",
        )
        self.assertEqual(document_fingerprint(document), document_fingerprint(document))

    def test_preparation_writes_combined_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingestion = root / "rss_ingestion" / "run-1" / "source"
            ingestion.mkdir(parents=True)
            (ingestion / "items.jsonl").write_text(json.dumps(article_value()) + "\n", encoding="utf-8")
            (ingestion.parent / "summary.json").write_text(
                json.dumps({"sources": [{"source_id": "source"}]}), encoding="utf-8"
            )
            documents, invalid_inputs = load_documents(
                ingestion.parent,
                DocumentPreparationConfig(ingestion_run_id="run-1", artifact_root=root),
            )
            result = run_document_preparation(
                config=DocumentPreparationConfig(ingestion_run_id="run-1", artifact_root=root),
                documents=documents,
                invalid_input_count=invalid_inputs,
                encoder=FakeEncoder(),
                entity_extractor=FakeExtractor(),
            )
            self.assertEqual(result.status, "ok")
            output = root / "document_preparation" / "run-1"
            feature = json.loads((output / "document_features.jsonl").read_text().splitlines()[0])
            self.assertEqual(feature["document"]["document_type"], "article")
            self.assertEqual(feature["embedding"]["model_name"], "fake-bge-m3")
            self.assertEqual(feature["entities"]["status"], "ok")

    def test_preparation_accepts_documents_loaded_by_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingestion = root / "rss_ingestion" / "run-1" / "source"
            ingestion.mkdir(parents=True)
            (ingestion / "items.jsonl").write_text(json.dumps(article_value()) + "\n", encoding="utf-8")
            (ingestion.parent / "summary.json").write_text(
                json.dumps({"sources": [{"source_id": "source"}]}), encoding="utf-8"
            )
            documents, invalid_inputs = load_documents(
                ingestion.parent,
                DocumentPreparationConfig(ingestion_run_id="run-1", artifact_root=root),
            )
            run_document_preparation(
                config=DocumentPreparationConfig(ingestion_run_id="run-1", artifact_root=root),
                documents=documents,
                invalid_input_count=invalid_inputs,
                encoder=FakeEncoder(),
                entity_extractor=FakeExtractor(),
            )
            document = json.loads(
                (root / "document_preparation" / "run-1" / "documents.jsonl")
                .read_text()
                .splitlines()[0]
            )
            self.assertEqual(document["title"], "Headline")

    def test_entity_failure_is_recorded_without_dropping_embedding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingestion = root / "rss_ingestion" / "run-1" / "source"
            ingestion.mkdir(parents=True)
            (ingestion / "items.jsonl").write_text(json.dumps(article_value()) + "\n", encoding="utf-8")
            (ingestion.parent / "summary.json").write_text(
                json.dumps({"sources": [{"source_id": "source"}]}), encoding="utf-8"
            )
            result = run_document_preparation(
                config=DocumentPreparationConfig(ingestion_run_id="run-1", artifact_root=root),
                documents=[RssArticleAdapter().adapt(article_value())],
                encoder=FakeEncoder(),
                entity_extractor=FailingExtractor(),
            )
            self.assertEqual(result.status, "partial")
            output = root / "document_preparation" / "run-1"
            feature = json.loads((output / "document_features.jsonl").read_text().splitlines()[0])
            self.assertEqual(feature["entities"]["status"], "failed")
            self.assertEqual(feature["status"], "ok")


def article_value() -> dict[str, object]:
    return {
        "article_id": "article-1",
        "source_id": "source",
        "source_name": "Source",
        "scope": "india-general",
        "category": "National",
        "title": "Headline",
        "description": "Description",
        "published_at": "2026-09-02T08:00:00+00:00",
        "url": "https://example.com/article-1",
        "tags": [],
        "ingested_at": "2026-09-02T08:05:00+00:00",
    }


def video_value() -> dict[str, object]:
    return {
        "document_id": "video-1",
        "document_type": "video",
        "source_id": "channel",
        "source_name": "Channel",
        "title": "Video headline",
        "summary": "Transcript summary",
        "published_at": "2026-09-02T08:00:00+00:00",
        "url": "https://example.com/video-1",
        "ingested_at": "2026-09-02T08:05:00+00:00",
    }


if __name__ == "__main__":
    unittest.main()
