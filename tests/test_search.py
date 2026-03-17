from cortex.models import Decision, Update
from cortex.state import StateManager


class TestSearchSingleWord:
    def test_finds_update_by_content_keyword(self, populated_state: StateManager):
        results = populated_state.search("docker")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "docker" in r.content.lower() for r in results)

    def test_finds_update_by_summary_keyword(self, populated_state: StateManager):
        results = populated_state.search("sandbox")
        assert len(results) >= 1

    def test_finds_decision_by_what_keyword(self, populated_state: StateManager):
        results = populated_state.search("WAL")
        assert len(results) >= 1
        assert any(isinstance(r, Decision) for r in results)

    def test_finds_decision_by_why_keyword(self, populated_state: StateManager):
        results = populated_state.search("concurrent")
        assert len(results) >= 1

    def test_empty_query_returns_empty(self, populated_state: StateManager):
        results = populated_state.search("")
        assert results == []

    def test_no_match_returns_empty(self, populated_state: StateManager):
        results = populated_state.search("nonexistentkeyword")
        assert results == []


class TestSearchMultiWord:
    def test_multi_word_finds_when_all_words_present(self, populated_state: StateManager):
        results = populated_state.search("docker sandbox")
        assert len(results) >= 1

    def test_multi_word_finds_words_in_different_fields(self, populated_state: StateManager):
        # "Docker" in content, "sandbox" in summary — both should match since OR across fields per token
        results = populated_state.search("docker setup")
        assert len(results) >= 1

    def test_multi_word_or_fallback_when_not_all_match(self, populated_state: StateManager):
        # AND finds nothing, OR fallback returns "docker" matches
        results = populated_state.search("docker kubernetes")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "docker" in r.content.lower() for r in results)

    def test_multi_word_across_update_content(self, populated_state: StateManager):
        results = populated_state.search("ralph loop workflow")
        assert len(results) >= 1

    def test_multi_word_decision_search(self, populated_state: StateManager):
        results = populated_state.search("WAL concurrent")
        assert len(results) >= 1


class TestSearchConsistency:
    def test_search_returns_results(self, populated_state: StateManager):
        results = populated_state.search("ralph")
        assert len(results) >= 1

    def test_search_returns_max_20_results(self, state: StateManager):
        stream = state.create_stream("Bulk test", ["test"])
        for i in range(25):
            state.add_update(stream.id, f"Update {i} about testing", f"Test update {i}")
        results = state.search("testing")
        assert len(results) <= 20

    def test_search_case_insensitive(self, populated_state: StateManager):
        results_lower = populated_state.search("docker")
        results_upper = populated_state.search("DOCKER")
        results_mixed = populated_state.search("Docker")
        assert len(results_lower) == len(results_upper) == len(results_mixed)
