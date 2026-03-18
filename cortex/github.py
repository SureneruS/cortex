from __future__ import annotations

import os
import subprocess

import httpx

_BASE = "https://api.github.com"
_GQL = "https://api.github.com/graphql"
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30)
    return _client


def _get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("No GITHUB_TOKEN env var and `gh auth token` failed") from exc


def _detect_repo() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    url = result.stdout.strip()
    # ssh: git@github.com:owner/repo.git
    if url.startswith("git@"):
        path = url.split(":", 1)[1]
    # https: https://github.com/owner/repo.git
    elif "github.com" in url:
        path = url.split("github.com/", 1)[1]
    else:
        raise RuntimeError(f"Cannot parse GitHub repo from remote URL: {url}")
    return path.removesuffix(".git")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+v3+json",
    }


def _rest_get(path: str, token: str) -> dict:
    resp = _get_client().get(f"{_BASE}{path}", headers=_headers(token))
    if not resp.is_success:
        raise RuntimeError(f"GitHub GET {path} failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _rest_post(path: str, token: str, data: dict) -> dict:
    resp = _get_client().post(f"{_BASE}{path}", headers=_headers(token), json=data)
    if not resp.is_success:
        raise RuntimeError(f"GitHub POST {path} failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _graphql(query: str, variables: dict, token: str) -> dict:
    resp = _get_client().post(
        _GQL,
        headers=_headers(token),
        json={"query": query, "variables": variables},
    )
    if not resp.is_success:
        raise RuntimeError(f"GitHub GraphQL failed ({resp.status_code}): {resp.text}")
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {body['errors']}")
    return body["data"]


def _split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    return owner, name


_PR_STATE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      state
      reviewDecision
      reviews(first: 100) { nodes { state author { login } submittedAt } }
      reviewThreads(first: 100) { totalCount nodes { isResolved } }
      comments { totalCount }
      commits(last: 1) {
        nodes {
          commit {
            committedDate
            statusCheckRollup {
              contexts(first: 100) {
                nodes {
                  ... on CheckRun { name conclusion status }
                  ... on StatusContext { context state }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def _compute_author_action(state: dict) -> tuple[bool, list[str]]:
    if state.get("state") in ("MERGED", "CLOSED"):
        return False, []

    reasons: list[str] = []

    ci = state.get("ciChecks", {})
    if any(v in ("FAILURE", "failure") for v in ci.values()):
        reasons.append("CI failing")

    unresolved = state.get("unresolvedThreadCount", 0)
    if unresolved > 0:
        reasons.append(f"{unresolved} unresolved thread(s)")

    if state.get("reviewDecision") == "CHANGES_REQUESTED":
        last_commit = state.get("lastCommitDate")
        reviews_with_ts = state.get("reviews", [])
        cr_dates = [
            r["submittedAt"]
            for r in reviews_with_ts
            if r["state"] == "CHANGES_REQUESTED" and r.get("submittedAt")
        ]
        if cr_dates and last_commit:
            latest_cr = max(cr_dates)
            if last_commit < latest_cr:
                reasons.append("Changes requested (not yet addressed)")
        elif not last_commit:
            reasons.append("Changes requested")

    ci_values = set(ci.values())
    all_ci_passed = ci_values and ci_values <= {
        "SUCCESS", "success", "NEUTRAL", "SKIPPED", "neutral", "skipped",
    }
    if (
        state.get("reviewDecision") == "APPROVED"
        and all_ci_passed
        and state.get("unresolvedThreadCount", 0) == 0
    ):
        reasons.append("Ready to merge")

    return bool(reasons), reasons


def pr_state(number: int, repo: str | None = None) -> dict:
    repo = repo or _detect_repo()
    owner, name = _split_repo(repo)
    token = _get_token()

    data = _graphql(
        _PR_STATE_QUERY,
        {"owner": owner, "repo": name, "number": number},
        token,
    )
    pr = data["repository"]["pullRequest"]

    ci_checks: dict[str, str] = {}
    commits = pr["commits"]["nodes"]
    last_commit_date: str | None = None
    if commits:
        last_commit_date = commits[0]["commit"].get("committedDate")
        rollup = commits[0]["commit"]["statusCheckRollup"]
        if rollup:
            for node in rollup["contexts"]["nodes"]:
                if "name" in node:
                    ci_checks[node["name"]] = node["conclusion"] or node["status"]
                elif "context" in node:
                    ci_checks[node["context"]] = node["state"]

    raw_reviews = pr["reviews"]["nodes"]
    reviews = [
        {
            "state": r["state"],
            "author": r["author"]["login"] if r.get("author") else None,
            "submittedAt": r.get("submittedAt"),
        }
        for r in raw_reviews
    ]

    thread_nodes = pr["reviewThreads"].get("nodes", [])
    unresolved_count = sum(1 for t in thread_nodes if not t.get("isResolved", True))

    state = {
        "state": pr["state"],
        "reviewDecision": pr["reviewDecision"],
        "commentCount": pr["comments"]["totalCount"],
        "reviewCount": len(raw_reviews),
        "reviewStates": [r["state"] for r in raw_reviews],
        "reviews": reviews,
        "lastCommitDate": last_commit_date,
        "unresolvedThreadCount": unresolved_count,
        "ciChecks": ci_checks,
    }

    needs_action, action_reasons = _compute_author_action(state)
    state["needsAuthorAction"] = needs_action
    state["actionReasons"] = action_reasons

    return state


_PR_THREADS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              databaseId
              author { login }
              body
              path
              line
            }
          }
        }
      }
    }
  }
}
"""


def pr_threads(number: int, repo: str | None = None) -> list[dict]:
    repo = repo or _detect_repo()
    owner, name = _split_repo(repo)
    token = _get_token()

    data = _graphql(
        _PR_THREADS_QUERY,
        {"owner": owner, "repo": name, "number": number},
        token,
    )
    threads = data["repository"]["pullRequest"]["reviewThreads"]["nodes"]

    result = []
    for t in threads:
        comments = t["comments"]["nodes"]
        if not comments:
            continue
        c = comments[0]
        result.append(
            {
                "thread_id": t["id"],
                "comment_id": c["databaseId"],
                "resolved": t["isResolved"],
                "author": c["author"]["login"] if c["author"] else None,
                "body": c["body"],
                "file": c["path"],
                "line": c["line"],
            }
        )
    return result


_PR_CHECKS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      commits(last: 1) {
        nodes {
          commit {
            statusCheckRollup {
              contexts(first: 100) {
                nodes {
                  ... on CheckRun {
                    name
                    conclusion
                    status
                    detailsUrl
                    startedAt
                    completedAt
                  }
                  ... on StatusContext {
                    context
                    state
                    targetUrl
                    createdAt
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def pr_checks(number: int, repo: str | None = None) -> list[dict]:
    repo = repo or _detect_repo()
    owner, name = _split_repo(repo)
    token = _get_token()

    data = _graphql(
        _PR_CHECKS_QUERY,
        {"owner": owner, "repo": name, "number": number},
        token,
    )
    commits = data["repository"]["pullRequest"]["commits"]["nodes"]
    if not commits:
        return []

    rollup = commits[0]["commit"]["statusCheckRollup"]
    if not rollup:
        return []

    result = []
    for node in rollup["contexts"]["nodes"]:
        if "name" in node:
            result.append(
                {
                    "name": node["name"],
                    "status": node["status"],
                    "conclusion": node["conclusion"],
                    "url": node.get("detailsUrl"),
                    "started_at": node.get("startedAt"),
                    "completed_at": node.get("completedAt"),
                }
            )
        elif "context" in node:
            result.append(
                {
                    "name": node["context"],
                    "status": node["state"],
                    "conclusion": node["state"],
                    "url": node.get("targetUrl"),
                    "started_at": node.get("createdAt"),
                    "completed_at": None,
                }
            )
    return result


def pr_react(
    number: int,
    comment_id: int,
    reaction: str,
    repo: str | None = None,
) -> dict:
    repo = repo or _detect_repo()
    token = _get_token()
    return _rest_post(
        f"/repos/{repo}/pulls/comments/{comment_id}/reactions",
        token,
        {"content": reaction},
    )


def pr_resolve(thread_id: str) -> dict:
    token = _get_token()
    mutation = """
    mutation($threadId: ID!) {
      resolveReviewThread(input: {threadId: $threadId}) {
        thread { id isResolved }
      }
    }
    """
    return _graphql(mutation, {"threadId": thread_id}, token)


def pr_reply(
    number: int,
    comment_id: int,
    body: str,
    repo: str | None = None,
) -> dict:
    repo = repo or _detect_repo()
    token = _get_token()
    return _rest_post(
        f"/repos/{repo}/pulls/{number}/comments/{comment_id}/replies",
        token,
        {"body": body},
    )
