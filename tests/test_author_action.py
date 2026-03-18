from __future__ import annotations

from cortex.github import _compute_author_action


def _make_state(**overrides: object) -> dict:
    base: dict = {
        "state": "OPEN",
        "reviewDecision": None,
        "commentCount": 0,
        "reviewCount": 0,
        "reviewStates": [],
        "reviews": [],
        "lastCommitDate": "2026-03-18T10:00:00Z",
        "unresolvedThreadCount": 0,
        "ciChecks": {},
    }
    base.update(overrides)
    return base


class TestComputeAuthorAction:
    def test_merged_pr(self) -> None:
        state = _make_state(state="MERGED")
        needs, reasons = _compute_author_action(state)
        assert needs is False
        assert reasons == []

    def test_closed_pr(self) -> None:
        state = _make_state(state="CLOSED")
        needs, reasons = _compute_author_action(state)
        assert needs is False
        assert reasons == []

    def test_ci_failing(self) -> None:
        state = _make_state(ciChecks={"tests": "FAILURE", "lint": "SUCCESS"})
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "CI failing" in reasons

    def test_changes_requested_not_addressed(self) -> None:
        state = _make_state(
            reviewDecision="CHANGES_REQUESTED",
            lastCommitDate="2026-03-18T09:00:00Z",
            reviews=[
                {
                    "state": "CHANGES_REQUESTED",
                    "author": "reviewer1",
                    "submittedAt": "2026-03-18T10:00:00Z",
                },
            ],
        )
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "Changes requested (not yet addressed)" in reasons

    def test_changes_requested_addressed(self) -> None:
        state = _make_state(
            reviewDecision="CHANGES_REQUESTED",
            lastCommitDate="2026-03-18T11:00:00Z",
            reviews=[
                {
                    "state": "CHANGES_REQUESTED",
                    "author": "reviewer1",
                    "submittedAt": "2026-03-18T10:00:00Z",
                },
            ],
        )
        needs, reasons = _compute_author_action(state)
        assert needs is False
        assert reasons == []

    def test_unresolved_threads(self) -> None:
        state = _make_state(unresolvedThreadCount=3)
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "3 unresolved thread(s)" in reasons

    def test_ready_to_merge(self) -> None:
        state = _make_state(
            reviewDecision="APPROVED",
            ciChecks={"tests": "SUCCESS", "lint": "SUCCESS"},
            unresolvedThreadCount=0,
        )
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "Ready to merge" in reasons

    def test_multiple_reasons(self) -> None:
        state = _make_state(
            ciChecks={"tests": "FAILURE"},
            unresolvedThreadCount=2,
        )
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "CI failing" in reasons
        assert "2 unresolved thread(s)" in reasons

    def test_addressed_changes_but_ci_failing(self) -> None:
        state = _make_state(
            reviewDecision="CHANGES_REQUESTED",
            lastCommitDate="2026-03-18T11:00:00Z",
            reviews=[
                {
                    "state": "CHANGES_REQUESTED",
                    "author": "reviewer1",
                    "submittedAt": "2026-03-18T10:00:00Z",
                },
            ],
            ciChecks={"tests": "FAILURE"},
        )
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "CI failing" in reasons
        assert "Changes requested (not yet addressed)" not in reasons

    def test_no_commit_date_with_changes_requested(self) -> None:
        state = _make_state(
            reviewDecision="CHANGES_REQUESTED",
            lastCommitDate=None,
            reviews=[
                {
                    "state": "CHANGES_REQUESTED",
                    "author": "reviewer1",
                    "submittedAt": "2026-03-18T10:00:00Z",
                },
            ],
        )
        needs, reasons = _compute_author_action(state)
        assert needs is True
        assert "Changes requested" in reasons

    def test_approved_but_ci_pending(self) -> None:
        state = _make_state(
            reviewDecision="APPROVED",
            ciChecks={"tests": "IN_PROGRESS"},
        )
        needs, reasons = _compute_author_action(state)
        assert needs is False
        assert "Ready to merge" not in reasons

    def test_open_pr_no_reviews_no_ci(self) -> None:
        state = _make_state()
        needs, reasons = _compute_author_action(state)
        assert needs is False
        assert reasons == []
