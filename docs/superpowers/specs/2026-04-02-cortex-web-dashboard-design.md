# Cortex Web Dashboard — Design Spec

## Overview

A web dashboard replacing the terminal TUI as the primary visual interface for Cortex. Provides mission control, messaging, settings management, and analytics across all Claude Code sessions. The unique value is **aggregate cross-session insights** — not just monitoring individual sessions, but surfacing actionable patterns across all sessions.

## Priority Order

1. **Analytics** — aggregate insights, failure patterns, friction points, resource usage
2. **Mission Control** — live session board with health, status, activity
3. **Messaging** — activity stream, channel messages, compose
4. **Settings** — CC config IDE with discovery of available options

## Architecture

### Stack

- **Backend**: Extend existing FastAPI (`cortex/api.py`). Python owns all MongoDB access. CLI and API share the same service layer — guaranteed parity.
- **Frontend**: React 19 + Vite + shadcn/ui + Tailwind CSS. TanStack Query for data fetching. Zustand for WebSocket state.
- **Real-time**: WebSocket (via FastAPI) for session status changes and channel messages. Everything else is near-real-time (poll/refresh).
- **Data sources**: MongoDB (session metadata, messages, aggregated analytics), JSONL files on demand (deep transcript replay).

### API Layer

Every CLI command has a corresponding API endpoint. The service layer is shared — `SessionService`, `MongoStateManager`, repositories are called by both CLI handlers and API route handlers.

WebSocket endpoint at `/ws` pushes:
- Session status changes (state machine transitions)
- Channel messages (new messages in any channel)
- Alert events (session died, daemon status change)

REST endpoints for everything else (CRUD operations, analytics queries, config reads/writes).

### MongoDB Abstraction

Current antipattern: direct MongoDB access scattered across the codebase. The dashboard project introduces a proper repository pattern for all collections, consumed by both CLI and API.

### JSONL Ingestion

Background job parses `~/.claude/projects/*/conversations/*.jsonl` and stores structured metadata in MongoDB:
- Per-session: tool call counts, failure rates, token breakdown, thinking token ratio, duration, files touched
- Aggregated: cross-session tool failure rates, resource usage by repo, efficiency metrics

Full transcript replay reads JSONL on demand (not stored in MongoDB).

## Navigation Model — The Zoom Stack

No sidebar navigation. No traditional SPA pages. The UI is a **layered stack** — zoom in for detail, zoom out for overview.

### Layers

- **Layer 0 (Board)**: Home screen. Session cards grouped by state + compressed activity stream panel on the right. KPI strip at top. Everything at a glance.
- **Layer 1 (Expand)**: Click a card → it expands inline with events, context bar, sparkline. Click a stream item → shows more detail with truncated content.
- **Layer 2 (Full View)**: Full-screen experiences — session introspection, full activity stream with rich content, settings overlay, analytics dashboard.

### Navigation

- **Click** = zoom in one layer
- **Esc** = zoom out one layer
- **Cmd+K** = teleport to any element at any layer (command palette)
- Top bar: logo, Cmd+K, toggle icons (stream panel, settings, analytics), + Spawn button

### Performance Requirements

- Virtualized lists (TanStack Virtual) — stream feeds and session grids render only visible items
- Optimistic UI — actions reflect instantly, sync in background
- Hardware-accelerated zoom transitions (CSS transforms, not layout)
- Lazy-load expensive components (syntax highlighting via Shiki, terminal via xterm.js)
- Zustand for WebSocket state — avoids re-rendering entire tree on real-time updates

## Feature Sections

### 1. Analytics (Top Priority)

**Philosophy**: Aggregate-first. Every metric is cross-session. Individual sessions are drill-down targets after spotting a pattern.

**KPI Row** (time range: 24h / 7d / 30d / All):
- Total sessions, total tokens, total cost, success rate, avg duration
- Each with sparkline trend and comparison to previous period

**Failure Hotspots**:
- Tool Call Failure Rate — table showing tool name, call count, fail%, top error message. Click row → shows failing sessions.
- Session Death Patterns — horizontal bar chart of death causes (test failure loop, context exhaustion, permission denied, unknown). Click bar → shows those sessions.

**Resource Usage**:
- Tokens by Repo — horizontal bars showing which repos consume the most
- Token Composition — stacked bar showing where tokens go (system prompt, thinking, tool I/O, output, user). With actionable insight text.
- Activity Heatmap — 24-hour grid showing when sessions are most active

**Efficiency & Friction**:
- Friction Points — alert-style cards surfacing specific actionable patterns:
  - "12 sessions ran failing tests 3+ times, avg 18k tokens wasted per loop"
  - "8 sessions read files >500 lines without offset/limit"
  - "6 sessions hit 95%+ context before finishing"
- Session Outcomes — completed / died / abandoned counts, broken down by repo
- Completion Rate by Repo — stacked bars (success/failure/abandoned)

**Data source**: MongoDB aggregations over ingested JSONL metadata. JSONL ingestion runs as a Cortex daemon cron job (every 5 minutes for active sessions, hourly full sweep). Analytics aggregations are precomputed on read with caching — not real-time, but fresh within minutes.

### 2. Mission Control

**Board View (Layer 0)**:
- KPI strip: active sessions, idle, hidden, tokens 24h, cost 24h
- Session cards grouped by state (Active, Watching & Idle, Hidden)
- Each card shows: name, color dot, goal, workspace, token count, duration, runtime state, activity sparkline
- Hover reveals action buttons (message, inspect, pause, close)

**Card Expand (Layer 1)**:
- Inline expansion showing: recent events timeline, context window gauge, linked items (stream, branch, PR, ticket)
- Quick actions without leaving the board

**Session Introspection (Layer 2)**:
- Three-column layout:
  - Left sidebar: session metadata, context gauge, linked items, event timeline, files touched (with edit/read/new badges)
  - Center: full transcript with tabs — Transcript, Tool Calls, Thinking, Messages, Diffs, **Config** (resolved settings for this session)
  - Right: context minimap (visual breakdown of what fills the context window), subagent list, task progress
- Transcript shows: user messages, thinking blocks (collapsible with token count), tool calls with syntax-highlighted diffs and output, assistant text with markdown rendering
- Actions in top bar: message, pause, close

**Resolved Config tab** (in session introspection):
- Shows the effective settings applied to this session after layering: global → project → user → session flags
- For each setting, shows the final value and which layer it came from (like Chrome DevTools computed CSS)
- Highlights overrides where a lower layer differs from a higher one

### 3. Messaging

**Activity Stream Panel (Layer 1)**:
- Right-side panel on the board, toggleable
- Chronological feed of all events: messages, tool calls, status changes, alerts, config changes
- Filter tabs: All / Messages / Alerts
- Truncated content with "expand" affordance
- Compose bar at bottom with recipient picker

**Full Stream View (Layer 2)**:
- Full-screen stream with rich content rendering:
  - Messages with complete text, markdown, code blocks with syntax highlighting
  - Thinking blocks with token counts
  - Error traces with full output
  - File diffs with add/remove highlighting
- Filter chips: All / Messages / Events / Alerts + session-specific filter
- Session scoping: click a session to see only its events
- Compose bar with recipient dropdown

**Message sending**: Always as "human" — the operator. Recipient picker shows all active sessions + "all" broadcast.

### 4. Settings

**Three-column layout**:
- Left nav: category tree (Config Files, Extensions, Automation, Access). Hierarchical navigation is natural for settings.
- Center: structured view of config files
  - Scope badges (global / project / user)
  - Key-value display with inline edit
  - MCP server status (running/stopped)
  - Hook definitions with matcher info
  - Permissions with allow/deny pill badges
- Right panel — Discovery:
  - Available but not configured options
  - "New in CC X.Y.Z" section highlighting recent additions
  - Click "+ add" to configure
  - Grouped by: available hooks, available settings, new features

**Search**: Top bar search across all settings, hooks, MCP servers, plugins, skills, agents.

**CC version awareness**: Badge showing current CC version. Discovery panel knows which features were added in which version. The available options catalog is maintained as a versioned JSON schema in the repo (`dashboard/data/cc-schema.json`), updated when CC releases new features. The dashboard reads this schema to populate the discovery panel.

## Global Elements

### Command Palette (Cmd+K)
- Search across: sessions (spawn, inspect, message), settings, analytics views, streams, recent activity
- Actions: spawn session, send message, open settings, jump to analytics
- Teleport to any layer from anywhere

### Notifications
- Toast notifications for real-time events: session died, message received for human, alert triggered
- Notification icon with badge count

### Status Bar
- Daemon health indicator
- Active session count
- CC version

## Scale Targets

- 5-10 concurrent users
- Up to 100 concurrent sessions
- Thousands of historical sessions for analytics
- WebSocket connections per user for real-time updates

## Mockups

Interactive mockups in `.superpowers/brainstorm/` (generated during design session):
- `mock-hybrid-ac.html` — Board + Activity Stream (Layer 0)
- `mock-zoom-layers.html` — The Zoom Stack concept (Layer 0 → 1 → 2)
- `mock-session-inspect.html` — Session Introspection (Layer 2)
- `mock-analytics.html` — Analytics Dashboard (Layer 2)
- `mock-settings.html` — Settings IDE (Layer 2)

## Project Structure

```
cortex/
├── dashboard/                  # Frontend (React + Vite)
│   ├── src/
│   │   ├── components/         # shadcn/ui + custom components
│   │   ├── features/           # Feature modules (analytics, board, stream, settings)
│   │   ├── hooks/              # React hooks (useWebSocket, useSession, etc.)
│   │   ├── stores/             # Zustand stores (websocket, sessions, stream)
│   │   ├── lib/                # Utilities, API client, types
│   │   └── App.tsx
│   ├── data/
│   │   └── cc-schema.json      # CC capabilities catalog (versioned)
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── cortex/
│   ├── api.py                  # FastAPI — extended with dashboard routes + WebSocket
│   ├── services/               # Shared service layer (CLI + API)
│   └── repositories/           # MongoDB repositories (shared)
```

## Out of Scope (for now)

- Authentication / RBAC (single-user to start, auth added when needed)
- Mobile responsive layout (desktop-first)
- Theme switching (dark mode only to start)
- Terminal embedding via xterm.js (future — attach to session in browser)
- Deployment infrastructure (local dev server, hosting decisions deferred)
