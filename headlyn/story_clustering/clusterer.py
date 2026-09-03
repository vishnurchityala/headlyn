from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from headlyn.story_index.hybrid_index import HybridStoryIndex

from .models import AssignmentResult, PreparedDocument, StoryClusteringConfig
from .scoring import score_candidate, select_best
from .updates import attach_document, create_singleton


class StoryClusterer:
    """Assign prepared documents to active stories through the hybrid index."""

    def __init__(
        self,
        *,
        index: HybridStoryIndex,
        config: StoryClusteringConfig,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.index = index
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def close_inactive(self) -> list[str]:
        """Close stories that have exceeded the configured inactivity window."""
        now = self.clock()
        cutoff = now - timedelta(hours=self.config.active_window_hours)
        closed: list[str] = []

        # Find stale active stories, close each one, and collect diagnostics.
        for story in self.index.get_active_stories():
            if story.last_updated_at < cutoff:
                self.index.mark_closed(story.story_id)
                closed.append(story.story_id)
        return closed

    def process_document(self, prepared: PreparedDocument) -> AssignmentResult:
        """Retrieve, score, and persist one prepared document assignment."""
        document = prepared.document
        now = self.clock()

        # Idempotency is checked before any retrieval or state mutation.
        if self.index.is_document_indexed(document.document_id):
            return AssignmentResult(
                document_id=document.document_id,
                story_id=None,
                decision="skipped",
                score=None,
                candidate_count=0,
                degraded=False,
                reason="document_already_indexed",
            )

        # Retrieve active dense and lexical candidates from the two adapters.
        candidates = self.index.search(
            prepared.encoded.canonical_text,
            prepared.encoded.dense_vector,
            dense_limit=self.config.dense_limit,
            lexical_limit=self.config.lexical_limit,
        )
        scores = []
        for candidate in candidates:
            story = self.index.get_story(candidate.story_id)
            if story is None or story.status != "active":
                continue
            scores.append(
                score_candidate(
                    candidate,
                    story,
                    prepared.entities,
                    now=now,
                    dense_limit=self.config.dense_limit,
                    lexical_limit=self.config.lexical_limit,
                    threshold=self.config.match_threshold,
                    semantic_weight=self.config.semantic_weight,
                    lexical_weight=self.config.lexical_weight,
                    entity_weight=self.config.entity_weight,
                    temporal_weight=self.config.temporal_weight,
                )
            )
        best = select_best(scores)

        # Attach to a sufficiently strong candidate or create a deterministic singleton.
        if best is not None and best.accepted:
            story = self.index.get_story(best.story_id)
            if story is None:
                raise RuntimeError(f"candidate story disappeared: {best.story_id}")
            updated = attach_document(story, prepared, now)
            self.index.upsert_story(updated, updated.representation(updated.centroid))
            return AssignmentResult(
                document_id=document.document_id,
                story_id=updated.story_id,
                decision="attached",
                score=best,
                candidate_count=len(scores),
                degraded=best.degraded,
            )

        singleton = create_singleton(prepared, now)
        self.index.upsert_story(singleton, singleton.representation(singleton.centroid))
        return AssignmentResult(
            document_id=document.document_id,
            story_id=singleton.story_id,
            decision="singleton",
            score=best,
            candidate_count=len(scores),
            degraded=prepared.entities.status != "ok",
            reason="no_candidate_above_threshold" if best else "no_active_candidates",
        )

    def process_batch(
        self,
        prepared_documents: Sequence[PreparedDocument],
        *,
        order_by_published_at: bool | None = None,
    ) -> list[AssignmentResult]:
        """Process documents serially, optionally sorting them chronologically."""
        # Close stale stories once before processing the batch.
        self.close_inactive()
        documents = list(prepared_documents)
        should_sort = (
            self.config.order_by_published_at
            if order_by_published_at is None
            else order_by_published_at
        )
        if should_sort:
            documents.sort(key=lambda item: item.document.published_at)

        # Serialize assignment writes so centroid updates cannot overwrite one another.
        return [self.process_document(prepared) for prepared in documents]
