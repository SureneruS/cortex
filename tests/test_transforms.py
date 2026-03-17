from cortex.transforms import apply_transform


def test_review_badge_approved():
    result = apply_transform("review_badge", {"reviewDecision": "APPROVED", "state": "OPEN"})
    assert result == {"text": "Approved", "color": "green"}


def test_review_badge_changes_requested():
    result = apply_transform(
        "review_badge", {"reviewDecision": "CHANGES_REQUESTED", "state": "OPEN"}
    )
    assert result == {"text": "Changes Requested", "color": "red"}


def test_review_badge_review_required():
    result = apply_transform("review_badge", {"reviewDecision": "REVIEW_REQUIRED", "state": "OPEN"})
    assert result == {"text": "Awaiting", "color": "yellow"}


def test_review_badge_no_decision():
    result = apply_transform("review_badge", {"reviewDecision": "", "state": "OPEN"})
    assert result == {"text": "Awaiting", "color": "yellow"}


def test_ci_badge_passing():
    result = apply_transform(
        "ci_badge", {"statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}]}
    )
    assert result == {"text": "Passing", "color": "green"}


def test_ci_badge_failing():
    result = apply_transform(
        "ci_badge", {"statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]}
    )
    assert result == {"text": "Failing", "color": "red"}


def test_ci_badge_pending():
    result = apply_transform(
        "ci_badge", {"statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": None}]}
    )
    assert result == {"text": "Pending", "color": "yellow"}


def test_pr_table_rows():
    prs = [
        {"number": 531, "title": "feat(ATS-661): ReBAC v2", "isDraft": True, "reviewDecision": ""},
        {
            "number": 548,
            "title": "feat(ATS-941): save draft",
            "isDraft": False,
            "reviewDecision": "APPROVED",
        },
    ]
    result = apply_transform("pr_table_rows", prs)
    assert len(result) == 2
    assert result[0][0] == "#531"
    assert result[0][2] == "Draft"
    assert result[1][3] == {"text": "Approved", "color": "green"}


def test_passthrough():
    data = {"anything": "goes"}
    result = apply_transform("passthrough", data)
    assert result == data


def test_unknown_transform():
    result = apply_transform("nonexistent", {"data": 1})
    assert result == {"data": 1}
