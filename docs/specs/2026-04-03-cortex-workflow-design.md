# Cortex Workflow — Design Spec

**Goal:** A skip-resilient, scope-adaptive feature-building workflow that replaces the superpowers pipeline. Owned entirely by the cortex plugin. Integrates with cortex sessions, channels, memory, and Linear.

**Principles:**
- User is the decision maker. Agent presents facts, observations, and constraints.
- No doc is authoritative unless user says so. Memory can be stale. Always confirm.
- Contracts (once agreed) are the source of truth for the current workflow.
- TDD always. Red-green at all scopes.
- Cortex is undercover — never referenced in external tools (Linear, Slack, PRs).
- Skip any phase. Workflow adapts without loss.

---

## Architecture

```
SessionStart hook (~50 lines, fires on startup + compact)
├── Workflow phase guide (which phase, how to scope)
├── Subagent escape hatch (workers skip this)
└── Cortex undercover rule

Phase skills (loaded on demand via Skill tool)
├── align     — facts, observations, contracts
├── plan      — plan artifact, always TDD, Linear sub-tickets
├── execute   — cortex dispatch, red-green cycle
└── close     — repo health, commit, PR, capture

Hooks (deterministic enforcement, zero token cost)
├── Verification gate — medium+ phases get external agent check
└── TBD: discovered during implementation

State layer (spike needed: file-first vs direct cortex)
├── Contracts + plan on disk (survive compaction, enable handoffs)
├── Workflow state (file or cortex — TBD after spike)
└── Cortex stream for logging progress
```

### Component Responsibilities

| Component | Type | When loaded | Token cost |
|-----------|------|-------------|------------|
| SessionStart hook | Hook | Every session + compact | ~50 lines injected |
| align skill | Skill | On demand (Skill tool) | ~100-200 lines |
| plan skill | Skill | On demand | ~100-200 lines |
| execute skill | Skill | On demand | ~100-200 lines |
| close skill | Skill | On demand | ~100-200 lines |
| Verification hook | Hook | Deterministic trigger | Zero (runs external agent) |

### Skip Resilience

No hard gates between phases. Any phase can be skipped. The workflow tracks what was skipped and adjusts:

- Skip align → plan phase asks for intent inline, contracts are minimal
- Skip plan → execute works from conversation context or user's verbal instructions
- Skip execute → close commits whatever is there
- Jump from align to execute → plan is implicit in the contracts
- Any fresh session can pick up by reading state + disk artifacts

---

## Phase 1: Align

**Purpose:** Build shared understanding of what needs to be built and why.

### Inputs
- Linear tickets (read via `linear-personal` MCP)
- Notion docs (via Notion MCP)
- Links and references
- User's task description
- Cortex memory (actively queried by component/module/tags — treated as potentially stale)

### Agent Behavior
- Present facts: what the codebase currently does, what the task requires, constraints, dependencies
- Surface observations: implications, risks, non-obvious things
- Query cortex memory for relevant past decisions, gotchas, patterns
- Ask clarifying questions: open-ended by default, multiple choice only for deterministic options
- Use AskUserQuestion tool for interaction
- When user asks for options: present neutrally with tradeoffs, no recommendation
- Push back with evidence when something won't work
- Be skeptical: no doc is source of truth unless user says so. Confirm when something seems off.

### Outputs — Contracts File
Written to disk (path TBD based on state spike). Contains:

- **Intent:** What we're building and why. Constraints. Out-of-scope.
- **Success criteria:** Concrete, verifiable conditions.
- **Verification commands:** How to prove it works (test commands, manual checks).
- **Scope assessment:** Lightweight / standard / deep. User's call, agent suggests based on observations.

### Linear Integration
When splitting work or finding trackable items during align:
- Create issues using the Linear issue template (see below)
- Suggest but wait for approval: acceptance criteria, priority, labels, estimates, related tickets
- Never add unapproved fields. Never reference cortex in Linear content.

### Scope Self-Assessment (this phase)
- **Lightweight:** 1-2 clarifying questions, contracts fit in 20 lines
- **Standard:** 3-5 questions, codebase research needed, detailed contracts
- **Deep:** Multiple rounds of exploration, external research, complex tradeoffs

---

## Phase 2: Plan

**Purpose:** Produce a plan artifact that any session (including fresh-context) can execute from.

### Always Exists
Scope affects depth, not whether a plan exists.
- Lightweight: ~50-line plan
- Standard: Detailed plan with file structure, test scenarios, multiple components
- Deep: Research phase first, architecture decisions documented, multiple implementation units

### Always TDD
Every plan includes red-green cycle:
1. Write failing test
2. Verify it fails (red)
3. Write minimal implementation
4. Verify it passes (green)
5. Refactor if needed
6. Repeat

### Plan Contents
- Files to create/modify (exact paths)
- Implementation steps (granularity scales with scope)
- Test strategy (TDD — tests first for every step)
- Verification commands (inherited from contracts)
- Dependencies and ordering

### Linear Sub-tickets
When splitting a feature into smaller units:
- Create issues using the Linear issue template
- Link to parent feature ticket
- Suggest acceptance criteria, priority, labels — wait for approval
- Never reference cortex

### Source Skepticism
- Codebase exploration is primary evidence
- Docs, memory, and external references are hints, not truth
- Confirm with user when something seems off or contradicts expectations

### Verification (medium+ scope)
External agent checks:
- Plan covers all contract success criteria
- No contract items are unaddressed
- Test strategy covers success criteria

---

## Phase 3: Execute

**Purpose:** Implement the plan.

### TDD at All Scopes
Red-green cycle is non-negotiable. Write test → see it fail → implement → see it pass.

### Dispatch Strategy (scales with scope)
- **Lightweight:** Implement in current session using plan mode
- **Standard:** Dispatch dev agent via `cortex session spawn` with plan + contracts
- **Deep:** Multiple workers via cortex, each handling an implementation unit

### Cortex Integration
- Workers spawned with `--worktree` for isolation
- Workers receive: plan artifact, contracts file, relevant cortex memory
- Workers report back via channels
- Progress logged to cortex stream
- Workflow state updated as implementation units complete

### Verification (medium+ scope)
External agent verifies implementation against contracts after each implementation unit:
- Do the tests cover the success criteria?
- Does the implementation match the intent?
- Any contract items missed?

---

## Phase 4: Close

**Purpose:** Ship, capture learnings, clean up.

### Step 1: Repo Health (before PR)
Update the repo with learnings from this work — for future sessions, not cortex memory:
- Update `CLAUDE.md` with relevant patterns, conventions, gotchas discovered
- Add `.claude/rules/` files for specific behavioral guidance
- These are repo-scoped and benefit all future sessions in that repo

### Step 2: Ship
- Commit with conventional format, linked to Linear ticket (`type(ATS-XXX): description`)
- Create PR (title format matches commit convention)

### Step 3: Capture to Cortex Memory
Structured capture (separate from repo health):
- What was learned (decisions, patterns, gotchas)
- What didn't work (anti-retry for future sessions)
- Component/module tags for active retrieval

### Step 4: Clean Up
- Worktree cleanup
- Workflow state marked complete
- Cortex stream updated

### Step 5: Offer Next Steps
- Babysit PR (existing `babysit-pr` skill)
- Check CI status
- Review comments

### Skip Resilience
If jumping straight to close from any phase:
- Commits what's there
- Creates PR from current state
- Still does repo health + capture
- Still cleans up

---

## Lateral: State Management

### Spike Required
Before committing to an approach, test two options:

**Option A — File-first:**
- Write state to `.workflow/state/<run-id>.json` on disk
- Background sync to cortex (MongoDB) periodically
- Fresh sessions read file first, fall back to cortex

**Option B — Cortex-direct:**
- Write state directly to cortex (MongoDB via CLI)
- Files on disk are only contracts + plan (not workflow state)
- Fresh sessions query cortex for workflow state

**Spike tests:** Latency per write, token cost (CLI invocation overhead), reliability, handoff experience.

### What State Tracks
- Current phase and phase history
- Scope assessment per phase
- Decisions made (with rationale)
- Skip decisions and overrides
- Verification results per phase
- Research findings (so fresh sessions don't re-research)
- What didn't work (anti-retry)

---

## Lateral: Enforcement via Hooks

### SessionStart Hook
- Injected on startup + compact (compaction-resilient)
- ~50 lines: phase descriptions, scope guidance, behavioral rules
- Subagent escape hatch: workers spawned for execution skip the workflow injection
- Cortex undercover rule reminder

### Verification Hook
- Medium+ scoped phases trigger external verification agent
- Agent checks output against contracts
- Hook event TBD (discovered during implementation — likely Stop or custom)

### TDD Enforcement
- Not via hook — enforced in plan structure
- Every plan includes red-green steps
- Verification agents check test-first ordering

---

## Lateral: Learning Integration

### Active Retrieval (align + plan phases)
- Query cortex memory by component, module, tags
- Surface relevant past decisions, gotchas, patterns
- All retrieved knowledge treated as potentially stale — confirm with user

### Structured Capture (close phase)
- Write to cortex memory with typed fields
- Include: what was learned, what didn't work, component/module tags
- Separate initiative to improve cortex memory structure (not part of this workflow build)

### Repo Health (close phase, separate from cortex memory)
- CLAUDE.md updates
- `.claude/rules/` files
- Committed to the repo — benefits all sessions, not just cortex-managed ones

---

## Linear Issue Template

Used whenever the workflow creates Linear issues (splitting features, tracking findings):

```
Title: Short, descriptive

Summary: 1-2 lines explaining the feature/bug

[Bug]
Reproducible steps:
1. ...
2. ...
(No assumptions. Examples stripped of real data.)

[Feature]
Relevant links: [Notion doc], [parent ticket], [reference]

---
Verified findings: [things confirmed by reading code or running tests]
User-approved decisions: [decisions made during align/plan]
```

**Suggested but requires approval:** acceptance criteria, priority, labels, estimates, related tickets

**Never included:** unverified suggestions, unverified findings, unverified assumptions, unapproved opinions, cortex references

---

## Implementation Approach

### Phase 1: Phase Skills
Build one skill at a time: align → plan → execute → close. Each ~100-200 lines.

### Phase 2: SessionStart Hook
Build the lightweight hook that replaces superpowers' hook. Fires on startup + compact.

### Phase 3: State Management Spike
Test file-first vs cortex-direct. Decision informs state layer implementation.

### Phase 4: Verification Hook
Implement the external agent gate for medium+ phases.

### Phase 5: Integration Testing
End-to-end test with a real feature task across the full workflow.
