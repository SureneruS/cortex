# Dashboard Phase 1: Foundation + Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the frontend scaffold and deliver the analytics dashboard — the highest-value feature that no other tool in the CC ecosystem provides.

**Architecture:** Extend existing FastAPI with analytics endpoints + WebSocket. New React+Vite frontend in `dashboard/`. JSONL ingestion job parses CC transcripts into MongoDB aggregates. Analytics UI reads from precomputed aggregations.

**Tech Stack:** React 19, Vite 6, shadcn/ui, Tailwind CSS 4, TanStack Query, Zustand, Recharts, FastAPI, WebSocket, MongoDB

---

## File Structure

```
dashboard/                          # NEW — React frontend
├── src/
│   ├── main.tsx                    # App entry
│   ├── App.tsx                     # Router + layout
│   ├── lib/
│   │   ├── api.ts                  # Fetch wrapper, base URL config
│   │   └── ws.ts                   # WebSocket client singleton
│   ├── stores/
│   │   └── realtime.ts             # Zustand store for WS events
│   ├── features/
│   │   └── analytics/
│   │       ├── AnalyticsPage.tsx    # Full analytics view (Layer 2)
│   │       ├── KpiRow.tsx           # KPI cards with sparklines
│   │       ├── FailureHotspots.tsx  # Tool failures + death patterns
│   │       ├── ResourceUsage.tsx    # Token breakdown, repo usage, heatmap
│   │       ├── FrictionPoints.tsx   # Actionable friction insights
│   │       └── hooks.ts            # useAnalytics, useTimeRange
│   └── components/
│       └── ui/                     # shadcn components (generated)
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── tsconfig.app.json
├── package.json
└── components.json                 # shadcn config

cortex/
├── api.py                          # MODIFY — add WebSocket + analytics router
├── api_analytics.py                # NEW — analytics REST endpoints
├── api_ws.py                       # NEW — WebSocket endpoint
├── services/
│   ├── analytics_service.py        # NEW — aggregation logic
│   └── jsonl_service.py            # NEW — JSONL parsing + ingestion
├── repositories/
│   └── analytics_repo.py           # NEW — analytics MongoDB collections
└── domain/
    └── analytics_models.py         # NEW — analytics dataclasses

tests/
├── test_jsonl_service.py           # NEW
├── test_analytics_service.py       # NEW
├── test_analytics_repo.py          # NEW
└── test_api_analytics.py           # NEW
```

---

### Task 1: Frontend Scaffold

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tailwind.config.ts`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/tsconfig.app.json`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/lib/api.ts`
- Create: `dashboard/components.json`

- [ ] **Step 1: Initialize Vite React project**

```bash
cd /Users/suren/workspace/cercli/cortex
npm create vite@latest dashboard -- --template react-ts
cd dashboard
npm install
```

- [ ] **Step 2: Install core dependencies**

```bash
cd /Users/suren/workspace/cercli/cortex/dashboard
npm install tailwindcss @tailwindcss/vite
npm install @tanstack/react-query zustand recharts
npm install clsx tailwind-merge class-variance-authority lucide-react
```

- [ ] **Step 3: Configure Tailwind with Vite plugin**

Replace `dashboard/vite.config.ts`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8420",
      "/ws": { target: "ws://localhost:8420", ws: true },
    },
  },
});
```

Replace `dashboard/src/index.css`:
```css
@import "tailwindcss";
```

- [ ] **Step 4: Initialize shadcn/ui**

```bash
cd /Users/suren/workspace/cercli/cortex/dashboard
npx shadcn@latest init -d
```

When prompted, select: New York style, Zinc color, CSS variables enabled.

Then install the components we need:
```bash
npx shadcn@latest add card badge button separator tabs tooltip
```

- [ ] **Step 5: Create API client utility**

Create `dashboard/src/lib/api.ts`:
```typescript
const BASE = "";

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

- [ ] **Step 6: Create minimal App with placeholder**

Replace `dashboard/src/App.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <div className="min-h-screen bg-background text-foreground p-6">
        <h1 className="text-2xl font-bold">Cortex Dashboard</h1>
        <p className="text-muted-foreground mt-2">Foundation loaded.</p>
      </div>
    </QueryClientProvider>
  );
}
```

Replace `dashboard/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 7: Verify it builds and runs**

```bash
cd /Users/suren/workspace/cercli/cortex/dashboard
npm run dev
```

Open http://localhost:5173 — should see "Cortex Dashboard" with "Foundation loaded." in dark theme.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat: scaffold React+Vite+shadcn frontend"
```

---

### Task 2: JSONL Parser Library

**Files:**
- Create: `cortex/services/jsonl_service.py`
- Create: `cortex/domain/analytics_models.py`
- Test: `tests/test_jsonl_service.py`

- [ ] **Step 1: Define analytics domain models**

Create `cortex/domain/analytics_models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    success: bool
    duration_ms: int
    error: str | None = None
    file_path: str | None = None


@dataclass(frozen=True)
class SessionAnalytics:
    session_id: str
    project_path: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int
    total_input_tokens: int
    total_output_tokens: int
    thinking_tokens: int
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_edited: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    compaction_count: int = 0
    max_context_usage: float = 0.0
    outcome: str = "unknown"  # completed, died, abandoned
    model: str = "unknown"
    cost_usd: float = 0.0
```

- [ ] **Step 2: Write failing test for JSONL parsing**

Create `tests/test_jsonl_service.py`:
```python
import json
import tempfile
from pathlib import Path

from cortex.services.jsonl_service import parse_jsonl_session


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_parse_extracts_tool_calls():
    entries = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "id": "t1",
                        "input": {"file_path": "/foo/bar.py"},
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            "timestamp": "2026-04-02T10:00:00Z",
        },
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "is_error": False,
            "duration_ms": 12,
            "timestamp": "2026-04-02T10:00:01Z",
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
        path = Path(f.name)

    result = parse_jsonl_session(path)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "Read"
    assert result.tool_calls[0].success is True
    assert result.tool_calls[0].duration_ms == 12


def test_parse_counts_tokens():
    entries = [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
            "timestamp": "2026-04-02T10:00:00Z",
        },
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "thinking", "thinking": "hmm"}],
                "usage": {"input_tokens": 500, "output_tokens": 800},
            },
            "timestamp": "2026-04-02T10:01:00Z",
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
        path = Path(f.name)

    result = parse_jsonl_session(path)
    assert result.total_input_tokens == 1500
    assert result.total_output_tokens == 1000
    assert result.thinking_tokens > 0


def test_parse_detects_failed_tool_calls():
    entries = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "id": "t2", "input": {"command": "pytest"}}
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            "timestamp": "2026-04-02T10:00:00Z",
        },
        {
            "type": "tool_result",
            "tool_use_id": "t2",
            "is_error": True,
            "content": "exit code 1",
            "duration_ms": 2400,
            "timestamp": "2026-04-02T10:00:03Z",
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
        path = Path(f.name)

    result = parse_jsonl_session(path)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].success is False
    assert result.tool_calls[0].error == "exit code 1"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/suren/workspace/cercli/cortex
uv run python -m pytest tests/test_jsonl_service.py -v
```

Expected: ImportError — `jsonl_service` does not exist yet.

- [ ] **Step 4: Implement JSONL parser**

Create `cortex/services/jsonl_service.py`:
```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cortex.domain.analytics_models import SessionAnalytics, ToolCallRecord

# Pricing per 1M tokens (opus)
_INPUT_COST = 15.0
_OUTPUT_COST = 75.0


def parse_jsonl_session(path: Path) -> SessionAnalytics:
    entries = _read_entries(path)
    if not entries:
        return _empty(path)

    tool_uses: dict[str, dict] = {}
    tool_calls: list[ToolCallRecord] = []
    files_read: list[str] = []
    files_edited: list[str] = []
    files_created: list[str] = []
    total_input = 0
    total_output = 0
    thinking_tokens = 0
    compactions = 0
    model = "unknown"
    timestamps: list[str] = []

    for entry in entries:
        ts = entry.get("timestamp")
        if ts:
            timestamps.append(ts)

        etype = entry.get("type", "")

        if etype == "assistant":
            msg = entry.get("message", {})
            usage = msg.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)

            if msg.get("model"):
                model = msg["model"]

            for block in msg.get("content", []):
                btype = block.get("type", "")
                if btype == "tool_use":
                    tool_uses[block["id"]] = block
                elif btype == "thinking":
                    text = block.get("thinking", "")
                    thinking_tokens += len(text) // 4  # rough estimate

        elif etype == "tool_result":
            tu_id = entry.get("tool_use_id", "")
            tu = tool_uses.pop(tu_id, None)
            if tu:
                name = tu.get("name", "unknown")
                is_error = entry.get("is_error", False)
                error_text = entry.get("content", "") if is_error else None
                if isinstance(error_text, list):
                    error_text = str(error_text)
                duration = entry.get("duration_ms", 0)
                inp = tu.get("input", {})
                fpath = inp.get("file_path") or inp.get("path")

                tool_calls.append(ToolCallRecord(
                    tool_name=name,
                    success=not is_error,
                    duration_ms=duration,
                    error=error_text if is_error else None,
                    file_path=fpath,
                ))

                if not is_error:
                    if name == "Read":
                        if fpath:
                            files_read.append(fpath)
                    elif name == "Edit":
                        if fpath:
                            files_edited.append(fpath)
                    elif name == "Write":
                        if fpath:
                            files_created.append(fpath)

        elif etype == "summary" or "compact" in etype.lower():
            compactions += 1

    started_at = _parse_ts(timestamps[0]) if timestamps else datetime.now(timezone.utc)
    ended_at = _parse_ts(timestamps[-1]) if len(timestamps) > 1 else None
    duration = int((ended_at - started_at).total_seconds()) if ended_at else 0

    cost = (total_input / 1_000_000) * _INPUT_COST + (total_output / 1_000_000) * _OUTPUT_COST

    return SessionAnalytics(
        session_id=path.stem,
        project_path=str(path.parent.parent),
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        thinking_tokens=thinking_tokens,
        tool_calls=tool_calls,
        files_read=list(set(files_read)),
        files_edited=list(set(files_edited)),
        files_created=list(set(files_created)),
        compaction_count=compactions,
        max_context_usage=0.0,
        outcome="unknown",
        model=model,
        cost_usd=round(cost, 4),
    )


def _read_entries(path: Path) -> list[dict]:
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def _empty(path: Path) -> SessionAnalytics:
    now = datetime.now(timezone.utc)
    return SessionAnalytics(
        session_id=path.stem,
        project_path=str(path.parent.parent),
        started_at=now,
        ended_at=None,
        duration_seconds=0,
        total_input_tokens=0,
        total_output_tokens=0,
        thinking_tokens=0,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/suren/workspace/cercli/cortex
uv run python -m pytest tests/test_jsonl_service.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cortex/domain/analytics_models.py cortex/services/jsonl_service.py tests/test_jsonl_service.py
git commit -m "feat: add JSONL parser for CC session transcripts"
```

---

### Task 3: Analytics Repository

**Files:**
- Create: `cortex/repositories/analytics_repo.py`
- Test: `tests/test_analytics_repo.py`

- [ ] **Step 1: Write failing test for storing and querying analytics**

Create `tests/test_analytics_repo.py`:
```python
from datetime import datetime, timezone

import pytest

from cortex.repositories.analytics_repo import MongoAnalyticsRepository


@pytest.fixture
def repo():
    from cortex.db import get_db
    db = get_db("cortex_test")
    r = MongoAnalyticsRepository(db)
    r._col.drop()
    yield r
    r._col.drop()


def test_upsert_and_get_session_analytics(repo: MongoAnalyticsRepository):
    doc = {
        "session_id": "abc-123",
        "project_path": "/home/user/.claude/projects/foo",
        "started_at": datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
        "duration_seconds": 600,
        "total_input_tokens": 50000,
        "total_output_tokens": 10000,
        "thinking_tokens": 5000,
        "tool_calls": [
            {"tool_name": "Read", "success": True, "duration_ms": 12},
            {"tool_name": "Bash", "success": False, "duration_ms": 2400, "error": "exit 1"},
        ],
        "model": "claude-opus-4-6",
        "cost_usd": 1.50,
        "outcome": "completed",
    }
    repo.upsert(doc)
    result = repo.get("abc-123")
    assert result is not None
    assert result["session_id"] == "abc-123"
    assert result["total_input_tokens"] == 50000
    assert len(result["tool_calls"]) == 2


def test_aggregate_tool_failures(repo: MongoAnalyticsRepository):
    for i in range(3):
        repo.upsert({
            "session_id": f"s-{i}",
            "project_path": "/p",
            "started_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "duration_seconds": 300,
            "total_input_tokens": 10000,
            "total_output_tokens": 2000,
            "thinking_tokens": 1000,
            "tool_calls": [
                {"tool_name": "Bash", "success": False, "duration_ms": 100, "error": "exit 1"},
                {"tool_name": "Read", "success": True, "duration_ms": 10},
                {"tool_name": "Bash", "success": True, "duration_ms": 50},
            ],
            "model": "opus",
            "cost_usd": 0.50,
            "outcome": "completed",
        })

    result = repo.aggregate_tool_failures()
    bash_entry = next(r for r in result if r["tool_name"] == "Bash")
    assert bash_entry["total_calls"] == 6
    assert bash_entry["failures"] == 3
    assert bash_entry["failure_rate"] == pytest.approx(0.5, abs=0.01)


def test_aggregate_kpis(repo: MongoAnalyticsRepository):
    for i in range(5):
        repo.upsert({
            "session_id": f"s-{i}",
            "project_path": "/p",
            "started_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "duration_seconds": 600,
            "total_input_tokens": 100000,
            "total_output_tokens": 20000,
            "thinking_tokens": 10000,
            "tool_calls": [],
            "model": "opus",
            "cost_usd": 2.0,
            "outcome": "completed" if i < 4 else "died",
        })

    kpis = repo.aggregate_kpis()
    assert kpis["total_sessions"] == 5
    assert kpis["total_tokens"] == 600000
    assert kpis["total_cost"] == pytest.approx(10.0)
    assert kpis["success_rate"] == pytest.approx(0.8)
    assert kpis["avg_duration_seconds"] == 600
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_analytics_repo.py -v
```

Expected: ImportError — `analytics_repo` does not exist.

- [ ] **Step 3: Implement analytics repository**

Create `cortex/repositories/analytics_repo.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from cortex.observability import trace


class MongoAnalyticsRepository:
    def __init__(self, db: Database) -> None:
        self._col = db["session_analytics"]
        self._col.create_index("session_id", unique=True)
        self._col.create_index("started_at")
        self._col.create_index("project_path")

    @trace
    def upsert(self, doc: dict[str, Any]) -> None:
        self._col.update_one(
            {"session_id": doc["session_id"]},
            {"$set": doc, "$setOnInsert": {"ingested_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    @trace
    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._col.find_one({"session_id": session_id}, {"_id": 0})

    @trace
    def aggregate_tool_failures(
        self, *, after: datetime | None = None
    ) -> list[dict[str, Any]]:
        match: dict = {}
        if after:
            match["started_at"] = {"$gte": after}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.extend([
            {"$unwind": "$tool_calls"},
            {
                "$group": {
                    "_id": "$tool_calls.tool_name",
                    "total_calls": {"$sum": 1},
                    "failures": {
                        "$sum": {"$cond": [{"$eq": ["$tool_calls.success", False]}, 1, 0]}
                    },
                    "top_errors": {
                        "$push": {
                            "$cond": [
                                {"$eq": ["$tool_calls.success", False]},
                                "$tool_calls.error",
                                "$$REMOVE",
                            ]
                        }
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "tool_name": "$_id",
                    "total_calls": 1,
                    "failures": 1,
                    "failure_rate": {
                        "$cond": [
                            {"$gt": ["$total_calls", 0]},
                            {"$divide": ["$failures", "$total_calls"]},
                            0,
                        ]
                    },
                    "top_errors": {"$slice": ["$top_errors", 5]},
                }
            },
            {"$sort": {"failure_rate": -1}},
        ])

        return list(self._col.aggregate(pipeline))

    @trace
    def aggregate_kpis(
        self, *, after: datetime | None = None
    ) -> dict[str, Any]:
        match: dict = {}
        if after:
            match["started_at"] = {"$gte": after}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.append({
            "$group": {
                "_id": None,
                "total_sessions": {"$sum": 1},
                "total_input": {"$sum": "$total_input_tokens"},
                "total_output": {"$sum": "$total_output_tokens"},
                "total_cost": {"$sum": "$cost_usd"},
                "avg_duration_seconds": {"$avg": "$duration_seconds"},
                "completed": {
                    "$sum": {"$cond": [{"$eq": ["$outcome", "completed"]}, 1, 0]}
                },
                "died": {
                    "$sum": {"$cond": [{"$eq": ["$outcome", "died"]}, 1, 0]}
                },
                "abandoned": {
                    "$sum": {"$cond": [{"$eq": ["$outcome", "abandoned"]}, 1, 0]}
                },
            }
        })

        results = list(self._col.aggregate(pipeline))
        if not results:
            return {
                "total_sessions": 0, "total_tokens": 0, "total_cost": 0.0,
                "success_rate": 0.0, "avg_duration_seconds": 0,
                "completed": 0, "died": 0, "abandoned": 0,
            }

        r = results[0]
        total = r["total_sessions"]
        return {
            "total_sessions": total,
            "total_tokens": r["total_input"] + r["total_output"],
            "total_cost": round(r["total_cost"], 2),
            "success_rate": round(r["completed"] / total, 2) if total else 0.0,
            "avg_duration_seconds": round(r["avg_duration_seconds"]),
            "completed": r["completed"],
            "died": r["died"],
            "abandoned": r["abandoned"],
        }

    @trace
    def aggregate_tokens_by_project(
        self, *, after: datetime | None = None
    ) -> list[dict[str, Any]]:
        match: dict = {}
        if after:
            match["started_at"] = {"$gte": after}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.extend([
            {
                "$group": {
                    "_id": "$project_path",
                    "total_tokens": {
                        "$sum": {"$add": ["$total_input_tokens", "$total_output_tokens"]}
                    },
                    "total_cost": {"$sum": "$cost_usd"},
                    "session_count": {"$sum": 1},
                }
            },
            {"$sort": {"total_tokens": -1}},
            {"$project": {"_id": 0, "project_path": "$_id", "total_tokens": 1, "total_cost": 1, "session_count": 1}},
        ])

        return list(self._col.aggregate(pipeline))

    @trace
    def aggregate_session_outcomes(
        self, *, after: datetime | None = None
    ) -> list[dict[str, Any]]:
        match: dict = {}
        if after:
            match["started_at"] = {"$gte": after}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.extend([
            {
                "$group": {
                    "_id": {"project": "$project_path", "outcome": "$outcome"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.project": 1, "count": -1}},
            {
                "$project": {
                    "_id": 0,
                    "project_path": "$_id.project",
                    "outcome": "$_id.outcome",
                    "count": 1,
                }
            },
        ])

        return list(self._col.aggregate(pipeline))

    @trace
    def aggregate_hourly_activity(
        self, *, after: datetime | None = None
    ) -> list[dict[str, Any]]:
        match: dict = {}
        if after:
            match["started_at"] = {"$gte": after}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.extend([
            {"$project": {"hour": {"$hour": "$started_at"}, "tokens": {"$add": ["$total_input_tokens", "$total_output_tokens"]}}},
            {"$group": {"_id": "$hour", "total_tokens": {"$sum": "$tokens"}, "session_count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "hour": "$_id", "total_tokens": 1, "session_count": 1}},
        ])

        return list(self._col.aggregate(pipeline))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_analytics_repo.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cortex/repositories/analytics_repo.py tests/test_analytics_repo.py
git commit -m "feat: add analytics repository with aggregation pipelines"
```

---

### Task 4: Analytics Service + Ingestion

**Files:**
- Create: `cortex/services/analytics_service.py`
- Modify: `cortex/container.py`
- Test: `tests/test_analytics_service.py`

- [ ] **Step 1: Write failing test for analytics service**

Create `tests/test_analytics_service.py`:
```python
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex.services.analytics_service import AnalyticsService
from cortex.repositories.analytics_repo import MongoAnalyticsRepository


@pytest.fixture
def repo():
    from cortex.db import get_db
    db = get_db("cortex_test")
    r = MongoAnalyticsRepository(db)
    r._col.drop()
    yield r
    r._col.drop()


@pytest.fixture
def service(repo):
    return AnalyticsService(repo)


def _make_jsonl(entries: list[dict]) -> Path:
    d = tempfile.mkdtemp()
    p = Path(d) / "conversations" / "test-session.jsonl"
    p.parent.mkdir(parents=True)
    with open(p, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def test_ingest_session(service: AnalyticsService, repo: MongoAnalyticsRepository):
    path = _make_jsonl([
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
            "timestamp": "2026-04-01T10:00:00Z",
        },
    ])
    service.ingest_session(path)
    result = repo.get(path.stem)
    assert result is not None
    assert result["total_input_tokens"] == 1000


def test_get_dashboard_data(service: AnalyticsService, repo: MongoAnalyticsRepository):
    for i in range(3):
        repo.upsert({
            "session_id": f"s-{i}",
            "project_path": "/p/cortex",
            "started_at": datetime(2026, 4, 1, 10 + i, 0, tzinfo=timezone.utc),
            "duration_seconds": 600,
            "total_input_tokens": 100000,
            "total_output_tokens": 20000,
            "thinking_tokens": 5000,
            "tool_calls": [
                {"tool_name": "Bash", "success": False, "duration_ms": 100, "error": "exit 1"},
                {"tool_name": "Read", "success": True, "duration_ms": 10},
            ],
            "model": "opus",
            "cost_usd": 2.0,
            "outcome": "completed",
        })

    data = service.get_dashboard_data()
    assert data["kpis"]["total_sessions"] == 3
    assert len(data["tool_failures"]) > 0
    assert len(data["tokens_by_project"]) > 0
    assert len(data["hourly_activity"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/test_analytics_service.py -v
```

Expected: ImportError — `analytics_service` does not exist.

- [ ] **Step 3: Implement analytics service**

Create `cortex/services/analytics_service.py`:
```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from cortex.observability import trace
from cortex.repositories.analytics_repo import MongoAnalyticsRepository
from cortex.services.jsonl_service import parse_jsonl_session


class AnalyticsService:
    def __init__(self, analytics_repo: MongoAnalyticsRepository) -> None:
        self._repo = analytics_repo

    @trace
    def ingest_session(self, jsonl_path: Path) -> None:
        analytics = parse_jsonl_session(jsonl_path)
        doc = asdict(analytics)
        doc["tool_calls"] = [asdict(tc) for tc in analytics.tool_calls]
        self._repo.upsert(doc)

    @trace
    def ingest_all(self, base_dir: Path | None = None) -> int:
        if base_dir is None:
            base_dir = Path.home() / ".claude" / "projects"

        count = 0
        if not base_dir.exists():
            return count

        for jsonl_path in base_dir.rglob("*.jsonl"):
            if "conversations" not in str(jsonl_path):
                continue
            self.ingest_session(jsonl_path)
            count += 1
        return count

    @trace
    def get_dashboard_data(
        self, *, time_range: str = "7d"
    ) -> dict[str, Any]:
        after = _parse_time_range(time_range)
        return {
            "kpis": self._repo.aggregate_kpis(after=after),
            "tool_failures": self._repo.aggregate_tool_failures(after=after),
            "tokens_by_project": self._repo.aggregate_tokens_by_project(after=after),
            "session_outcomes": self._repo.aggregate_session_outcomes(after=after),
            "hourly_activity": self._repo.aggregate_hourly_activity(after=after),
            "time_range": time_range,
        }


def _parse_time_range(tr: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if tr == "24h":
        return now - timedelta(hours=24)
    elif tr == "7d":
        return now - timedelta(days=7)
    elif tr == "30d":
        return now - timedelta(days=30)
    return None
```

- [ ] **Step 4: Wire into container**

Add to the imports and `__init__` in `cortex/container.py`:

Add import:
```python
from cortex.repositories.analytics_repo import MongoAnalyticsRepository
from cortex.services.analytics_service import AnalyticsService
```

Add to `Container.__init__`:
```python
self.analytics: MongoAnalyticsRepository = MongoAnalyticsRepository(db)
self.analytics_service: AnalyticsService = AnalyticsService(self.analytics)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_analytics_service.py -v
```

Expected: All 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cortex/services/analytics_service.py cortex/container.py tests/test_analytics_service.py
git commit -m "feat: add analytics service with JSONL ingestion and aggregation"
```

---

### Task 5: Analytics API Endpoints

**Files:**
- Create: `cortex/api_analytics.py`
- Modify: `cortex/api.py`
- Test: `tests/test_api_analytics.py`

- [ ] **Step 1: Write failing test for analytics endpoints**

Create `tests/test_api_analytics.py`:
```python
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from cortex.api import app
from cortex.container import get_container, reset_container


@pytest.fixture(autouse=True)
def _clean():
    reset_container()
    yield
    reset_container()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def _seed_data():
    c = get_container()
    for i in range(5):
        c.analytics.upsert({
            "session_id": f"s-{i}",
            "project_path": f"/home/user/.claude/projects/repo-{i % 2}",
            "started_at": datetime(2026, 4, 1, 10 + i, 0, tzinfo=timezone.utc),
            "duration_seconds": 600,
            "total_input_tokens": 100000,
            "total_output_tokens": 20000,
            "thinking_tokens": 5000,
            "tool_calls": [
                {"tool_name": "Bash", "success": False, "duration_ms": 100, "error": "exit 1"},
                {"tool_name": "Read", "success": True, "duration_ms": 10},
            ],
            "model": "opus",
            "cost_usd": 2.0,
            "outcome": "completed" if i < 4 else "died",
        })


def test_get_analytics_dashboard(client: TestClient, _seed_data):
    resp = client.get("/api/analytics/dashboard?time_range=all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["total_sessions"] == 5
    assert len(data["tool_failures"]) > 0


def test_get_analytics_kpis(client: TestClient, _seed_data):
    resp = client.get("/api/analytics/kpis?time_range=all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 5
    assert data["total_cost"] == pytest.approx(10.0)


def test_get_analytics_tool_failures(client: TestClient, _seed_data):
    resp = client.get("/api/analytics/tool-failures?time_range=all")
    assert resp.status_code == 200
    data = resp.json()
    bash_entry = next(r for r in data if r["tool_name"] == "Bash")
    assert bash_entry["failures"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/test_api_analytics.py -v
```

Expected: 404 — routes don't exist yet.

- [ ] **Step 3: Implement analytics router**

Create `cortex/api_analytics.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Query

from cortex.container import get_container

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
def get_dashboard(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    svc = get_container().analytics_service
    return svc.get_dashboard_data(time_range=time_range)


@router.get("/kpis")
def get_kpis(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    repo = get_container().analytics
    after = _parse_after(time_range)
    return repo.aggregate_kpis(after=after)


@router.get("/tool-failures")
def get_tool_failures(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    repo = get_container().analytics
    after = _parse_after(time_range)
    return repo.aggregate_tool_failures(after=after)


@router.get("/tokens-by-project")
def get_tokens_by_project(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    repo = get_container().analytics
    after = _parse_after(time_range)
    return repo.aggregate_tokens_by_project(after=after)


@router.get("/session-outcomes")
def get_session_outcomes(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    repo = get_container().analytics
    after = _parse_after(time_range)
    return repo.aggregate_session_outcomes(after=after)


@router.get("/hourly-activity")
def get_hourly_activity(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    repo = get_container().analytics
    after = _parse_after(time_range)
    return repo.aggregate_hourly_activity(after=after)


@router.post("/ingest")
def trigger_ingest():
    svc = get_container().analytics_service
    count = svc.ingest_all()
    return {"ingested": count}


def _parse_after(tr: str):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    if tr == "24h":
        return now - timedelta(hours=24)
    elif tr == "7d":
        return now - timedelta(days=7)
    elif tr == "30d":
        return now - timedelta(days=30)
    return None
```

- [ ] **Step 4: Register router in api.py**

Add to `cortex/api.py` imports:
```python
from cortex.api_analytics import router as analytics_router
```

Add after the existing `app.include_router(dashboard_router)` line:
```python
app.include_router(analytics_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_api_analytics.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cortex/api_analytics.py cortex/api.py tests/test_api_analytics.py
git commit -m "feat: add analytics REST API endpoints"
```

---

### Task 6: WebSocket Infrastructure

**Files:**
- Create: `cortex/api_ws.py`
- Create: `dashboard/src/lib/ws.ts`
- Create: `dashboard/src/stores/realtime.ts`
- Modify: `cortex/api.py`

- [ ] **Step 1: Implement WebSocket endpoint**

Create `cortex/api_ws.py`:
```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_connections: set[WebSocket] = set()


async def broadcast(event_type: str, data: dict[str, Any]) -> None:
    payload = json.dumps({"type": event_type, "data": data})
    stale: list[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _connections.discard(ws)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connections.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _connections.discard(ws)
```

- [ ] **Step 2: Register WebSocket router in api.py**

Add to `cortex/api.py` imports:
```python
from cortex.api_ws import router as ws_router
```

Add after the analytics router include:
```python
app.include_router(ws_router)
```

- [ ] **Step 3: Create frontend WebSocket client**

Create `dashboard/src/lib/ws.ts`:
```typescript
type Listener = (event: { type: string; data: unknown }) => void;

let socket: WebSocket | null = null;
const listeners = new Set<Listener>();

export function connectWs(): void {
  if (socket?.readyState === WebSocket.OPEN) return;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/ws`;
  socket = new WebSocket(url);

  socket.onmessage = (ev) => {
    try {
      const parsed = JSON.parse(ev.data);
      listeners.forEach((fn) => fn(parsed));
    } catch {
      /* ignore malformed */
    }
  };

  socket.onclose = () => {
    socket = null;
    setTimeout(connectWs, 3000);
  };
}

export function onWsEvent(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
```

- [ ] **Step 4: Create Zustand realtime store**

Create `dashboard/src/stores/realtime.ts`:
```typescript
import { create } from "zustand";
import { connectWs, onWsEvent } from "@/lib/ws";

interface RealtimeEvent {
  type: string;
  data: unknown;
  receivedAt: number;
}

interface RealtimeStore {
  events: RealtimeEvent[];
  connected: boolean;
  init: () => void;
}

export const useRealtime = create<RealtimeStore>((set) => ({
  events: [],
  connected: false,

  init: () => {
    connectWs();
    onWsEvent((ev) => {
      set((s) => ({
        connected: true,
        events: [...s.events.slice(-99), { ...ev, receivedAt: Date.now() }],
      }));
    });
  },
}));
```

- [ ] **Step 5: Commit**

```bash
git add cortex/api_ws.py cortex/api.py dashboard/src/lib/ws.ts dashboard/src/stores/realtime.ts
git commit -m "feat: add WebSocket infrastructure (backend + frontend)"
```

---

### Task 7: Analytics Dashboard UI — KPI Row

**Files:**
- Create: `dashboard/src/features/analytics/hooks.ts`
- Create: `dashboard/src/features/analytics/KpiRow.tsx`
- Create: `dashboard/src/features/analytics/AnalyticsPage.tsx`
- Modify: `dashboard/src/App.tsx`

- [ ] **Step 1: Create analytics data hooks**

Create `dashboard/src/features/analytics/hooks.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useState } from "react";

export type TimeRange = "24h" | "7d" | "30d" | "all";

export function useTimeRange() {
  const [range, setRange] = useState<TimeRange>("7d");
  return { range, setRange };
}

export function useAnalyticsDashboard(range: TimeRange) {
  return useQuery({
    queryKey: ["analytics", "dashboard", range],
    queryFn: () => apiFetch<AnalyticsDashboard>(`/api/analytics/dashboard?time_range=${range}`),
    refetchInterval: 60_000,
  });
}

export interface AnalyticsDashboard {
  kpis: {
    total_sessions: number;
    total_tokens: number;
    total_cost: number;
    success_rate: number;
    avg_duration_seconds: number;
    completed: number;
    died: number;
    abandoned: number;
  };
  tool_failures: ToolFailure[];
  tokens_by_project: TokensByProject[];
  session_outcomes: SessionOutcome[];
  hourly_activity: HourlyActivity[];
  time_range: string;
}

export interface ToolFailure {
  tool_name: string;
  total_calls: number;
  failures: number;
  failure_rate: number;
  top_errors: string[];
}

export interface TokensByProject {
  project_path: string;
  total_tokens: number;
  total_cost: number;
  session_count: number;
}

export interface SessionOutcome {
  project_path: string;
  outcome: string;
  count: number;
}

export interface HourlyActivity {
  hour: number;
  total_tokens: number;
  session_count: number;
}
```

- [ ] **Step 2: Create KPI row component**

Create `dashboard/src/features/analytics/KpiRow.tsx`:
```tsx
import { Card } from "@/components/ui/card";

interface Kpi {
  label: string;
  value: string;
  change?: string;
  changeType?: "up" | "down" | "neutral";
}

export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="grid grid-cols-5 gap-3">
      {kpis.map((kpi) => (
        <Card key={kpi.label} className="p-4 bg-card/50 border-border/50">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {kpi.label}
          </p>
          <p className="text-2xl font-bold mt-1">{kpi.value}</p>
          {kpi.change && (
            <p
              className={`text-xs mt-0.5 ${
                kpi.changeType === "up"
                  ? "text-green-500"
                  : kpi.changeType === "down"
                    ? "text-red-500"
                    : "text-muted-foreground"
              }`}
            >
              {kpi.change}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create analytics page shell**

Create `dashboard/src/features/analytics/AnalyticsPage.tsx`:
```tsx
import { useAnalyticsDashboard, useTimeRange } from "./hooks";
import { KpiRow } from "./KpiRow";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

function formatDuration(seconds: number): string {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 60)}m`;
}

const TIME_OPTIONS = ["24h", "7d", "30d", "all"] as const;

export function AnalyticsPage() {
  const { range, setRange } = useTimeRange();
  const { data, isLoading } = useAnalyticsDashboard(range);

  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-muted-foreground">
        Loading analytics...
      </div>
    );
  }

  const { kpis } = data;

  const kpiItems = [
    { label: "Sessions", value: String(kpis.total_sessions) },
    { label: "Total Tokens", value: formatTokens(kpis.total_tokens) },
    { label: "Total Cost", value: `$${kpis.total_cost.toFixed(2)}` },
    {
      label: "Success Rate",
      value: `${Math.round(kpis.success_rate * 100)}%`,
      changeType: kpis.success_rate >= 0.8 ? "up" as const : "down" as const,
    },
    { label: "Avg Duration", value: formatDuration(kpis.avg_duration_seconds) },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="sticky top-0 z-10 h-11 flex items-center px-5 bg-background/95 backdrop-blur border-b border-border/50">
        <button onClick={() => {}} className="text-xs text-muted-foreground mr-4">
          ← Board
        </button>
        <h1 className="text-sm font-bold">Analytics</h1>
        <div className="ml-auto flex gap-0.5 bg-muted/30 rounded-md p-0.5">
          {TIME_OPTIONS.map((t) => (
            <button
              key={t}
              onClick={() => setRange(t)}
              className={`text-[10px] px-2.5 py-1 rounded ${
                range === t
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="p-6 max-w-[1400px] mx-auto space-y-6">
        <KpiRow kpis={kpiItems} />
        {/* FailureHotspots, ResourceUsage, FrictionPoints will go here */}
        <p className="text-muted-foreground text-sm">
          More sections coming in subsequent tasks.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire analytics page into App**

Replace `dashboard/src/App.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AnalyticsPage />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: Verify it renders**

Run both backend and frontend:
```bash
# Terminal 1: backend
cd /Users/suren/workspace/cercli/cortex
uv run uvicorn cortex.api:app --port 8420

# Terminal 2: frontend
cd /Users/suren/workspace/cercli/cortex/dashboard
npm run dev
```

Open http://localhost:5173 — should see the analytics page with KPI cards (loading state or zeros if no data yet).

Trigger ingestion:
```bash
curl -X POST http://localhost:8420/api/analytics/ingest
```

Refresh — KPI cards should populate with real data from your JSONL files.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/features/analytics/ dashboard/src/App.tsx
git commit -m "feat: analytics page with KPI row"
```

---

### Task 8: Analytics — Failure Hotspots

**Files:**
- Create: `dashboard/src/features/analytics/FailureHotspots.tsx`
- Modify: `dashboard/src/features/analytics/AnalyticsPage.tsx`

- [ ] **Step 1: Create FailureHotspots component**

Create `dashboard/src/features/analytics/FailureHotspots.tsx`:
```tsx
import { Card } from "@/components/ui/card";
import type { ToolFailure } from "./hooks";

function failColor(rate: number): string {
  if (rate >= 0.1) return "text-red-500";
  if (rate >= 0.05) return "text-orange-400";
  return "text-green-500";
}

export function FailureHotspots({ toolFailures, kpis }: {
  toolFailures: ToolFailure[];
  kpis: { died: number; completed: number; abandoned: number };
}) {
  const totalDead = kpis.died;
  const totalCompleted = kpis.completed;
  const totalAbandoned = kpis.abandoned;
  const totalSessions = totalDead + totalCompleted + totalAbandoned;

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-sm font-semibold">Failure Hotspots</h2>
        <p className="text-xs text-muted-foreground">Where things break across all sessions</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4 bg-card/50 border-border/50">
          <h3 className="text-xs font-semibold mb-1">Tool Call Failure Rate</h3>
          <p className="text-[10px] text-muted-foreground mb-3">
            Across {totalSessions} sessions
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border/50">
                <th className="text-left pb-2 text-[9px] uppercase tracking-wider text-muted-foreground font-normal">Tool</th>
                <th className="text-left pb-2 text-[9px] uppercase tracking-wider text-muted-foreground font-normal">Calls</th>
                <th className="text-left pb-2 text-[9px] uppercase tracking-wider text-muted-foreground font-normal">Fail%</th>
                <th className="text-left pb-2 text-[9px] uppercase tracking-wider text-muted-foreground font-normal">Top Error</th>
              </tr>
            </thead>
            <tbody>
              {toolFailures.map((tf) => (
                <tr key={tf.tool_name} className="border-b border-border/30 hover:bg-muted/20 cursor-pointer">
                  <td className="py-2 font-semibold">{tf.tool_name}</td>
                  <td className="py-2 text-muted-foreground">{tf.total_calls}</td>
                  <td className="py-2">
                    <span className={`font-semibold tabular-nums ${failColor(tf.failure_rate)}`}>
                      {(tf.failure_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2 text-muted-foreground text-[10px] max-w-[200px] truncate">
                    {tf.top_errors[0] ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="p-4 bg-card/50 border-border/50">
          <h3 className="text-xs font-semibold mb-1">Session Outcomes</h3>
          <p className="text-[10px] text-muted-foreground mb-3">
            {totalSessions} sessions total
          </p>
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 bg-muted/20 rounded-lg">
              <p className="text-2xl font-bold text-green-500">{totalCompleted}</p>
              <p className="text-[10px] text-muted-foreground">Completed</p>
            </div>
            <div className="text-center p-3 bg-muted/20 rounded-lg">
              <p className="text-2xl font-bold text-red-500">{totalDead}</p>
              <p className="text-[10px] text-muted-foreground">Died</p>
            </div>
            <div className="text-center p-3 bg-muted/20 rounded-lg">
              <p className="text-2xl font-bold text-muted-foreground">{totalAbandoned}</p>
              <p className="text-[10px] text-muted-foreground">Abandoned</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add to AnalyticsPage**

In `dashboard/src/features/analytics/AnalyticsPage.tsx`, add import:
```typescript
import { FailureHotspots } from "./FailureHotspots";
```

Replace the placeholder comment and `<p>` tag with:
```tsx
<FailureHotspots toolFailures={data.tool_failures} kpis={kpis} />
```

- [ ] **Step 3: Verify it renders with real data**

Refresh http://localhost:5173 — should see tool failure table and session outcome cards below the KPIs.

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/features/analytics/
git commit -m "feat: analytics failure hotspots and session outcomes"
```

---

### Task 9: Analytics — Resource Usage

**Files:**
- Create: `dashboard/src/features/analytics/ResourceUsage.tsx`
- Modify: `dashboard/src/features/analytics/AnalyticsPage.tsx`

- [ ] **Step 1: Create ResourceUsage component**

Create `dashboard/src/features/analytics/ResourceUsage.tsx`:
```tsx
import { Card } from "@/components/ui/card";
import type { TokensByProject, HourlyActivity } from "./hooks";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

function projectName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

export function ResourceUsage({ tokensByProject, hourlyActivity }: {
  tokensByProject: TokensByProject[];
  hourlyActivity: HourlyActivity[];
}) {
  const maxTokens = Math.max(...tokensByProject.map((p) => p.total_tokens), 1);
  const maxHourly = Math.max(...hourlyActivity.map((h) => h.total_tokens), 1);

  const colors = [
    "bg-blue-500/40", "bg-orange-400/40", "bg-green-500/40",
    "bg-yellow-400/40", "bg-purple-400/40",
  ];

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-sm font-semibold">Resource Usage</h2>
        <p className="text-xs text-muted-foreground">Where tokens and time go</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4 bg-card/50 border-border/50">
          <h3 className="text-xs font-semibold mb-1">Tokens by Repo</h3>
          <p className="text-[10px] text-muted-foreground mb-3">Which repos consume the most</p>
          <div className="space-y-2">
            {tokensByProject.map((p, i) => (
              <div key={p.project_path} className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground w-24 text-right truncate">
                  {projectName(p.project_path)}
                </span>
                <div className="flex-1 h-5 bg-muted/20 rounded overflow-hidden">
                  <div
                    className={`h-full rounded flex items-center pl-2 text-[9px] font-semibold ${colors[i % colors.length]}`}
                    style={{ width: `${(p.total_tokens / maxTokens) * 100}%` }}
                  >
                    {formatTokens(p.total_tokens)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-4 bg-card/50 border-border/50">
          <h3 className="text-xs font-semibold mb-1">Activity by Hour</h3>
          <p className="text-[10px] text-muted-foreground mb-3">Token volume distribution</p>
          <div className="flex items-end gap-[2px] h-[120px]">
            {Array.from({ length: 24 }, (_, h) => {
              const entry = hourlyActivity.find((a) => a.hour === h);
              const tokens = entry?.total_tokens ?? 0;
              const pct = (tokens / maxHourly) * 100;
              const opacity = Math.max(0.05, pct / 100);
              return (
                <div
                  key={h}
                  className="flex-1 rounded-sm"
                  style={{
                    height: `${Math.max(2, pct)}%`,
                    backgroundColor: `rgba(99, 179, 237, ${opacity})`,
                  }}
                  title={`${h}:00 — ${formatTokens(tokens)}`}
                />
              );
            })}
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[8px] text-muted-foreground">12am</span>
            <span className="text-[8px] text-muted-foreground">6am</span>
            <span className="text-[8px] text-muted-foreground">12pm</span>
            <span className="text-[8px] text-muted-foreground">6pm</span>
            <span className="text-[8px] text-muted-foreground">11pm</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add to AnalyticsPage**

Import and add after FailureHotspots:
```tsx
import { ResourceUsage } from "./ResourceUsage";

// After <FailureHotspots ... />
<ResourceUsage
  tokensByProject={data.tokens_by_project}
  hourlyActivity={data.hourly_activity}
/>
```

- [ ] **Step 3: Verify and commit**

Refresh http://localhost:5173 — should see tokens by repo bars and hourly activity heatmap.

```bash
git add dashboard/src/features/analytics/
git commit -m "feat: analytics resource usage charts"
```

---

### Task 10: Analytics — Friction Points

**Files:**
- Create: `cortex/services/friction_analyzer.py`
- Create: `cortex/api_analytics.py` (modify — add friction endpoint)
- Create: `dashboard/src/features/analytics/FrictionPoints.tsx`
- Modify: `dashboard/src/features/analytics/AnalyticsPage.tsx`
- Modify: `dashboard/src/features/analytics/hooks.ts`
- Test: `tests/test_friction_analyzer.py`

- [ ] **Step 1: Write failing test for friction analysis**

Create `tests/test_friction_analyzer.py`:
```python
from cortex.services.friction_analyzer import analyze_friction


def test_detects_retry_loops():
    sessions = [
        {
            "session_id": "s-1",
            "project_path": "/p/cortex",
            "tool_calls": [
                {"tool_name": "Bash", "success": False, "duration_ms": 2000, "error": "exit 1"},
                {"tool_name": "Bash", "success": False, "duration_ms": 2000, "error": "exit 1"},
                {"tool_name": "Bash", "success": False, "duration_ms": 2000, "error": "exit 1"},
                {"tool_name": "Bash", "success": True, "duration_ms": 2000},
            ],
            "total_input_tokens": 50000,
            "total_output_tokens": 10000,
        },
    ]
    frictions = analyze_friction(sessions)
    retry_frictions = [f for f in frictions if f["type"] == "retry_loop"]
    assert len(retry_frictions) == 1
    assert retry_frictions[0]["session_count"] >= 1


def test_detects_large_file_reads():
    sessions = [
        {
            "session_id": "s-1",
            "project_path": "/p/cortex",
            "tool_calls": [
                {"tool_name": "Read", "success": True, "duration_ms": 50, "file_path": "/big.py"},
                {"tool_name": "Read", "success": True, "duration_ms": 50, "file_path": "/big.py"},
                {"tool_name": "Read", "success": True, "duration_ms": 50, "file_path": "/big.py"},
            ],
            "total_input_tokens": 200000,
            "total_output_tokens": 10000,
        },
    ]
    frictions = analyze_friction(sessions)
    read_frictions = [f for f in frictions if f["type"] == "repeated_reads"]
    assert len(read_frictions) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/test_friction_analyzer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement friction analyzer**

Create `cortex/services/friction_analyzer.py`:
```python
from __future__ import annotations

from collections import Counter
from typing import Any


def analyze_friction(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frictions: list[dict[str, Any]] = []
    frictions.extend(_detect_retry_loops(sessions))
    frictions.extend(_detect_repeated_reads(sessions))
    frictions.extend(_detect_context_exhaustion(sessions))
    return sorted(frictions, key=lambda f: f["severity"], reverse=True)


def _detect_retry_loops(sessions: list[dict]) -> list[dict]:
    affected_sessions: list[str] = []
    total_wasted_tokens = 0

    for s in sessions:
        calls = s.get("tool_calls", [])
        consecutive_fails = 0
        max_streak = 0
        for c in calls:
            if not c.get("success", True):
                consecutive_fails += 1
                max_streak = max(max_streak, consecutive_fails)
            else:
                consecutive_fails = 0
        if max_streak >= 3:
            affected_sessions.append(s["session_id"])
            total_wasted_tokens += max_streak * 6000  # rough estimate

    if not affected_sessions:
        return []

    return [{
        "type": "retry_loop",
        "severity": 3,
        "title": "Retry loops on failing commands",
        "description": (
            f"{len(affected_sessions)} sessions ran the same failing command 3+ times "
            f"before changing approach. ~{total_wasted_tokens // 1000}k tokens wasted."
        ),
        "session_count": len(affected_sessions),
        "session_ids": affected_sessions,
        "projects": _unique_projects(sessions, affected_sessions),
    }]


def _detect_repeated_reads(sessions: list[dict]) -> list[dict]:
    affected_sessions: list[str] = []

    for s in sessions:
        calls = s.get("tool_calls", [])
        read_files = [c.get("file_path") for c in calls if c.get("tool_name") == "Read" and c.get("file_path")]
        counts = Counter(read_files)
        if any(v >= 3 for v in counts.values()):
            affected_sessions.append(s["session_id"])

    if not affected_sessions:
        return []

    return [{
        "type": "repeated_reads",
        "severity": 2,
        "title": "Reading the same files repeatedly",
        "description": (
            f"{len(affected_sessions)} sessions read the same file 3+ times. "
            f"Use offset/limit for large files."
        ),
        "session_count": len(affected_sessions),
        "session_ids": affected_sessions,
        "projects": _unique_projects(sessions, affected_sessions),
    }]


def _detect_context_exhaustion(sessions: list[dict]) -> list[dict]:
    affected_sessions: list[str] = []

    for s in sessions:
        max_ctx = s.get("max_context_usage", 0)
        compactions = s.get("compaction_count", 0)
        if max_ctx > 0.9 or compactions > 0:
            affected_sessions.append(s["session_id"])

    if not affected_sessions:
        return []

    return [{
        "type": "context_exhaustion",
        "severity": 2,
        "title": "Context exhaustion before task completion",
        "description": (
            f"{len(affected_sessions)} sessions hit 90%+ context or required compaction."
        ),
        "session_count": len(affected_sessions),
        "session_ids": affected_sessions,
        "projects": _unique_projects(sessions, affected_sessions),
    }]


def _unique_projects(sessions: list[dict], ids: list[str]) -> list[str]:
    return list({s["project_path"] for s in sessions if s["session_id"] in ids})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/test_friction_analyzer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Add friction endpoint to API**

Add to `cortex/api_analytics.py`:
```python
from cortex.services.friction_analyzer import analyze_friction

@router.get("/friction-points")
def get_friction_points(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    c = get_container()
    after = _parse_after(time_range)
    match = {}
    if after:
        match["started_at"] = {"$gte": after}
    sessions = list(c.analytics._col.find(match, {"_id": 0}))
    return analyze_friction(sessions)
```

Also update `get_dashboard` to include friction:
```python
@router.get("/dashboard")
def get_dashboard(time_range: str = Query("7d", pattern="^(24h|7d|30d|all)$")):
    svc = get_container().analytics_service
    data = svc.get_dashboard_data(time_range=time_range)
    after = _parse_after(time_range)
    match = {}
    if after:
        match["started_at"] = {"$gte": after}
    sessions = list(get_container().analytics._col.find(match, {"_id": 0}))
    data["friction_points"] = analyze_friction(sessions)
    return data
```

- [ ] **Step 6: Create FrictionPoints component**

Create `dashboard/src/features/analytics/FrictionPoints.tsx`:
```tsx
import { Card } from "@/components/ui/card";

interface FrictionPoint {
  type: string;
  severity: number;
  title: string;
  description: string;
  session_count: number;
  projects: string[];
}

const severityColors: Record<number, string> = {
  3: "border-red-500/20 bg-red-500/5",
  2: "border-yellow-500/20 bg-yellow-500/5",
  1: "border-orange-400/20 bg-orange-400/5",
};

const severityIcons: Record<number, string> = {
  3: "⚠",
  2: "⚠",
  1: "ℹ",
};

function projectName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

export function FrictionPoints({ points }: { points: FrictionPoint[] }) {
  if (points.length === 0) {
    return (
      <Card className="p-4 bg-card/50 border-border/50">
        <p className="text-sm text-muted-foreground">No friction points detected.</p>
      </Card>
    );
  }

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-sm font-semibold">Efficiency & Friction</h2>
        <p className="text-xs text-muted-foreground">Actionable patterns to improve session performance</p>
      </div>
      <div className="space-y-2">
        {points.map((p, i) => (
          <div
            key={i}
            className={`flex items-start gap-3 p-3 rounded-lg border ${severityColors[p.severity] ?? severityColors[1]}`}
          >
            <span className="text-base mt-0.5">{severityIcons[p.severity]}</span>
            <div>
              <p className="text-xs font-semibold">{p.title}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{p.description}</p>
              <p className="text-[9px] text-muted-foreground/60 mt-1">
                Seen in: {p.projects.map(projectName).join(", ")}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Update hooks and AnalyticsPage**

Add to the `AnalyticsDashboard` interface in `hooks.ts`:
```typescript
friction_points: FrictionPoint[];
```

Add the `FrictionPoint` interface:
```typescript
export interface FrictionPoint {
  type: string;
  severity: number;
  title: string;
  description: string;
  session_count: number;
  session_ids: string[];
  projects: string[];
}
```

Add to `AnalyticsPage.tsx`:
```tsx
import { FrictionPoints } from "./FrictionPoints";

// After <ResourceUsage ... />
<FrictionPoints points={data.friction_points} />
```

- [ ] **Step 8: Verify and commit**

```bash
git add cortex/services/friction_analyzer.py cortex/api_analytics.py tests/test_friction_analyzer.py dashboard/src/features/analytics/
git commit -m "feat: analytics friction points with actionable insights"
```

---

## Subsequent Plans

This plan delivers the **Foundation + Analytics** dashboard. The following phases are separate plans:

- **Phase 3: Mission Control** — Board view (Layer 0), session cards, expand (Layer 1), session introspection (Layer 2) with transcript replay
- **Phase 4: Messaging** — Activity stream panel, full stream view, compose bar, WebSocket message delivery
- **Phase 5: Settings** — Config IDE with three-column layout, discovery panel, CC schema catalog

Each phase builds on the foundation established here (frontend scaffold, API layer, WebSocket, Zustand store).
