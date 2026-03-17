from __future__ import annotations

from typing import Any


def _review_badge(data: dict) -> dict:
    decision = data.get("reviewDecision", "")
    mapping = {
        "APPROVED": {"text": "Approved", "color": "green"},
        "CHANGES_REQUESTED": {"text": "Changes Requested", "color": "red"},
    }
    return mapping.get(decision, {"text": "Awaiting", "color": "yellow"})


def _ci_badge(data: dict) -> dict:
    checks = data.get("statusCheckRollup", [])
    if not checks:
        return {"text": "None", "color": "muted"}
    conclusions = [c.get("conclusion") for c in checks]
    if any(c == "FAILURE" for c in conclusions):
        return {"text": "Failing", "color": "red"}
    if any(c is None for c in conclusions):
        return {"text": "Pending", "color": "yellow"}
    return {"text": "Passing", "color": "green"}


def _pr_table_rows(data: list) -> list:
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)
    standalone: list = []

    for pr in data:
        title = pr.get("title", "")
        ticket = ""
        if "(" in title and ")" in title:
            ticket = title[title.index("(") + 1 : title.index(")")]
        pr["_ticket"] = ticket
        if pr.get("isDraft") and ticket:
            groups[ticket].append(pr)
        else:
            standalone.append(pr)

    rows = []
    for pr in standalone:
        rows.append(_pr_to_row(pr))

    for ticket, prs in groups.items():
        if len(prs) == 1:
            rows.append(_pr_to_row(prs[0]))
        else:
            numbers = sorted(p["number"] for p in prs)
            first, last = numbers[0], numbers[-1]
            number_cell = {
                "text": f"#{first}..#{last}",
                "url": f"https://github.com/cercli/recruitment-backend/pull/{last}",
            }
            ticket_cell = {
                "text": ticket,
                "url": f"https://linear.app/cercli/issue/{ticket}" if ticket.startswith(("ATS-", "PLT-")) else None,
            }
            state = {"text": f"Draft ({len(prs)} PRs)", "color": "muted"}
            review = {"text": "—", "color": "muted"}
            ci = {"text": "—", "color": "muted"}
            rows.append([number_cell, ticket_cell, state, ci, review])

    return rows


def _pr_to_row(pr: dict) -> list:
    number = pr["number"]
    ticket = pr.get("_ticket", "")
    title = pr.get("title", "")
    # Short description: strip prefix like "feat(ATS-661): "
    desc = title
    if ":" in title:
        desc = title.split(":", 1)[1].strip()

    number_cell = {
        "text": f"#{number}",
        "url": f"https://github.com/cercli/recruitment-backend/pull/{number}",
    }
    ticket_cell = {
        "text": ticket or desc[:30],
        "url": f"https://linear.app/cercli/issue/{ticket}" if ticket.startswith(("ATS-", "PLT-")) else None,
    }
    is_draft = pr.get("isDraft", False)
    state = {"text": "Draft", "color": "muted"} if is_draft else {"text": "Ready", "color": "green"}
    ci = _ci_badge({"statusCheckRollup": pr.get("statusCheckRollup", [])})
    review = _review_badge({"reviewDecision": pr.get("reviewDecision", "")})
    return [number_cell, ticket_cell, state, ci, review]


def _passthrough(data):
    return data


TRANSFORMS = {
    "review_badge": _review_badge,
    "ci_badge": _ci_badge,
    "pr_table_rows": _pr_table_rows,
    "passthrough": _passthrough,
}


def apply_transform(name: str, data: Any) -> Any:
    fn = TRANSFORMS.get(name, _passthrough)
    return fn(data)
