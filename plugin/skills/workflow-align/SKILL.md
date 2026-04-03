---
name: workflow-align
description: Use when starting feature work, receiving a ticket, or beginning any non-trivial implementation task — before writing code or plans. Builds shared understanding and produces contracts.
---

# Align

Build shared understanding of what needs to be built. You present facts and observations. The user decides the approach.

## Inputs

Gather from whatever is available:
- Linear ticket (read via `linear-personal` MCP)
- Notion docs, links, references the user provides
- User's task description
- Cortex memory — query by component/module/tags for relevant past decisions and gotchas

## Critical: This is an interactive process

Each step below requires user input before moving to the next. Present your findings, then STOP and wait for the user to respond. Do NOT chain steps together autonomously. Do NOT propose designs or plans — that is a different phase.

## Process

### 1. Understand the Task

Read the inputs. Explore the relevant codebase areas. Then present:
- **Facts:** What the code currently does. What the task requires.
- **Observations:** Implications, risks, dependencies, non-obvious things.
- **Past learnings:** Relevant findings from cortex memory (flagged as potentially stale).

Do not propose solutions or approaches yet. The user needs the facts first.

**STOP here. Present findings and wait for user response.**

### 2. Clarify

Ask questions to fill gaps in understanding. Use AskUserQuestion tool.

- Open-ended by default
- Multiple choice only when options are deterministic (e.g., "which repo?" not "what approach?")
- One question at a time — wait for the answer before asking the next
- When the user asks for options: present neutrally with tradeoffs. No recommendations.
- Push back with evidence when something won't work. Correct the user when they're wrong.

**STOP after each question. Wait for the answer.**

### 3. Scope Assessment

Once the user confirms understanding is solid, suggest a scope level. The user can override.

| Level | Signal | Ceremony |
|-------|--------|----------|
| **Lightweight** | 1-3 files, clear implementation, well-understood domain | Short contracts, 50-line plan |
| **Standard** | Multiple components, some research needed, moderate complexity | Detailed contracts, full plan |
| **Deep** | Ambiguous requirements, external research, architectural decisions | Multiple rounds of exploration, comprehensive plan |

This is a global signal. Each subsequent phase independently assesses its own depth, using this as input.

### 4. Write Contracts

Only after the user has confirmed alignment on intent, scope, and success criteria. Do NOT write contracts based on your own assumptions.

Write a contracts file to disk. This becomes the source of truth for the workflow.

```
# Contracts: <task title>

## Intent
What we're building and why.
Constraints.
What is explicitly out of scope.

## Success Criteria
Success criteria describe WHAT the system should do, not HOW it's implemented.
Write from the user/stakeholder perspective — observable behaviors and requirements.
Implementation details (class names, method names, file structure) belong in the plan, not here.

Good: "Scheduling an interview sends an email to each interviewer with interview details"
Bad: "New send_batch method on ResendGateway using resend.Batch.send()"

- [ ] Requirement-based condition 1
- [ ] Requirement-based condition 2

## Verification
Commands or steps to prove it works:
- `pytest tests/path/test_file.py -v`
- Manual: verify X behaves as Y

## Scope
Overall: lightweight | standard | deep
```

Path: in the worktree root or a shared location readable by handoff sessions.

### 5. Linear Integration

When splitting work or discovering trackable items:

**Create issues using this template:**
```
Title: Short, descriptive

Summary: 1-2 lines — feature or bug description

[Bug] Reproducible steps (no assumptions, no real data in examples)
[Feature] Relevant links to resources

Verified findings: [confirmed by reading code or running tests]
```

- Suggest but wait for approval: acceptance criteria, priority, labels, estimates, related tickets
- Never add unapproved fields
- Never reference cortex in Linear content

## Skepticism Rule

- No doc is authoritative unless the user says so
- Memory can be stale — flag it, confirm with user
- When something seems off or contradicts expectations, stop and ask
- Codebase is primary evidence. Docs are hints.
- Contracts (once agreed) are the exception — they are the source of truth.

## What NOT to Do

- Do not propose approaches unsolicited. Present facts, let the user decide.
- Do not recommend "option B because..." — only present options when asked, and neutrally.
- Do not treat any external doc as authoritative without user confirmation.
- Do not skip writing contracts. Even lightweight scope gets a 10-line contracts file.
- Do not ask closed questions to narrow the solution space prematurely.
