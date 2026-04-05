from __future__ import annotations

from cortex.adapters.vector_store import SIMILARITY_THRESHOLD
from cortex.domain.models import Checkpoint, Decision, Update
from cortex.domain.protocols import CheckpointRepository, StreamRepository, VectorStore

SearchResult = Update | Decision | Checkpoint


class SearchService:
    """Orchestrates search across semantic, text, and regex strategies."""

    def __init__(
        self,
        streams: StreamRepository,
        checkpoints: CheckpointRepository,
        vector_store: VectorStore,
    ) -> None:
        self._streams = streams
        self._checkpoints = checkpoints
        self._vec = vector_store

    def search(self, query: str) -> list[SearchResult]:
        if self._vec.available:
            results = self._semantic_search(query)
            if results:
                return results
        results = self._text_search(query)
        if results:
            return results
        return self._regex_search(query)

    def _semantic_search(self, query: str) -> list[SearchResult]:
        vec_results = self._vec.search(query)
        if not vec_results or vec_results[0][2] > SIMILARITY_THRESHOLD:
            return []
        results: list[SearchResult] = []
        for entity_id, entity_type, distance in vec_results:
            if distance > SIMILARITY_THRESHOLD:
                break
            entity = self._hydrate(entity_id, entity_type)
            if entity:
                results.append(entity)
        return results

    def _text_search(self, query: str) -> list[SearchResult]:
        stream_results = self._streams.text_search(query)
        checkpoint_results = self._checkpoints.text_search(query)
        return (stream_results + checkpoint_results)[:20]

    def _regex_search(self, query: str) -> list[SearchResult]:
        stream_results = self._streams.regex_search(query)
        checkpoint_results = self._checkpoints.regex_search(query)
        combined = stream_results + checkpoint_results
        tokens = query.lower().split()

        def _match_count(item: SearchResult) -> int:
            if isinstance(item, Update):
                text = f"{item.content} {item.summary}".lower()
            elif isinstance(item, Decision):
                text = f"{item.what} {item.why}".lower()
            else:
                text = item.content.lower()
            return sum(1 for t in tokens if t in text)

        combined.sort(key=lambda x: (-_match_count(x), -x.created_at.timestamp()))
        return combined[:20]

    def _hydrate(self, entity_id: str, entity_type: str) -> SearchResult | None:
        if entity_type == "update":
            return self._streams.get_update_by_id(entity_id)
        elif entity_type == "decision":
            return self._streams.get_decision_by_id(entity_id)
        elif entity_type == "checkpoint":
            return self._checkpoints.get_by_id(entity_id)
        return None
