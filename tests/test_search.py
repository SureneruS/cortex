from cortex.container import Container
from cortex.domain.models import Decision, Update
from cortex.services.search_service import SearchService
from cortex.services.stream_service import StreamService


class TestSearchSingleWord:
    def test_finds_update_by_content_keyword(self, populated_container: Container):
        results = populated_container.search_service.search("docker")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "docker" in r.content.lower() for r in results)

    def test_finds_update_by_summary_keyword(self, populated_container: Container):
        results = populated_container.search_service.search("sandbox")
        assert len(results) >= 1

    def test_finds_decision_by_what_keyword(self, populated_container: Container):
        results = populated_container.search_service.search("WAL")
        assert len(results) >= 1
        assert any(isinstance(r, Decision) for r in results)

    def test_finds_decision_by_why_keyword(self, populated_container: Container):
        results = populated_container.search_service.search("concurrent")
        assert len(results) >= 1

    def test_empty_query_returns_empty(self, populated_container: Container):
        results = populated_container.search_service.search("")
        assert results == []

    def test_no_match_returns_empty(self, populated_container: Container):
        results = populated_container.search_service.search("nonexistentkeyword")
        assert results == []


class TestSearchMultiWord:
    def test_multi_word_finds_when_all_words_present(self, populated_container: Container):
        results = populated_container.search_service.search("docker sandbox")
        assert len(results) >= 1

    def test_multi_word_finds_words_in_different_fields(self, populated_container: Container):
        results = populated_container.search_service.search("docker setup")
        assert len(results) >= 1

    def test_multi_word_or_fallback_when_not_all_match(self, populated_container: Container):
        results = populated_container.search_service.search("docker kubernetes")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "docker" in r.content.lower() for r in results)

    def test_multi_word_across_update_content(self, populated_container: Container):
        results = populated_container.search_service.search("ralph loop workflow")
        assert len(results) >= 1

    def test_multi_word_decision_search(self, populated_container: Container):
        results = populated_container.search_service.search("WAL concurrent")
        assert len(results) >= 1


class TestSearchConsistency:
    def test_search_returns_results(self, populated_container: Container):
        results = populated_container.search_service.search("ralph")
        assert len(results) >= 1

    def test_search_returns_max_20_results(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Bulk test", ["test"])
        for i in range(25):
            stream_svc.add_update(stream.id, f"Update {i} about testing", f"Test update {i}")
        results = search_svc.search("testing")
        assert len(results) <= 20

    def test_search_case_insensitive(self, populated_container: Container):
        search = populated_container.search_service
        results_lower = search.search("docker")
        results_upper = search.search("DOCKER")
        results_mixed = search.search("Docker")
        assert len(results_lower) == len(results_upper) == len(results_mixed)
