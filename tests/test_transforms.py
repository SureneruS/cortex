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
    # PR 548 is standalone (not draft), PR 531 is draft+ticket → grouped after standalone
    assert result[0][0] == {"text": "#548", "url": "https://github.com/cercli/recruitment-backend/pull/548"}
    assert result[1][0] == {"text": "#531", "url": "https://github.com/cercli/recruitment-backend/pull/531"}
    assert result[1][2] == {"text": "Draft", "color": "muted"}
    assert result[0][4] == {"text": "Approved", "color": "green"}


def test_passthrough():
    data = {"anything": "goes"}
    result = apply_transform("passthrough", data)
    assert result == data


def test_unknown_transform():
    result = apply_transform("nonexistent", {"data": 1})
    assert result == {"data": 1}
