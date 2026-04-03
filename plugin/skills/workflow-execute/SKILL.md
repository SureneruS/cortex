---
name: workflow-execute
description: Use when a plan exists and you're ready to implement — after planning, before close. Dispatches work through cortex sessions scaled to scope.
---

# Execute

Implement the plan. Dispatch strategy scales with scope. TDD at all levels.

## Inputs

- Plan file (from plan phase)
- Contracts file (source of truth for success criteria)
- Cortex memory (relevant patterns — flagged as potentially stale)

## TDD — Non-negotiable

Every implementation step follows: write test → red → implement → green.

This applies regardless of scope, dispatch strategy, or who's doing the work (you, a spawned worker, or a subagent).

## Dispatch Strategy

Assess independently from the plan's scope. A deep plan may have straightforward implementation. A lightweight plan may need careful execution.

### Lightweight — Current Session

Implement directly in the current session using plan mode.

- Follow the plan steps in order
- Run tests after each step
- Commit at logical checkpoints

### Standard — Dispatch Dev Agent

Spawn a worker session via cortex with the plan and contracts.

```
cortex session spawn \
  --name <task-slug> \
  --repo <repo> \
  --worktree <task-slug> \
  --goal "<task summary>"
```

Send the worker:
- Path to plan file
- Path to contracts file
- Relevant cortex memory findings (copy the content — don't assume the worker can query cortex memory)

The worker executes the plan, reports back via channels. Monitor progress via `cortex session capture <name>`.

### Deep — Multiple Workers

For plans with independent implementation units, spawn one worker per unit.

```
cortex session spawn --name <task>-unit-1 --repo <repo> --worktree <task>-unit-1
cortex session spawn --name <task>-unit-2 --repo <repo> --worktree <task>-unit-2
```

Each worker gets:
- Their specific implementation unit from the plan
- The full contracts file (so they understand the bigger picture)
- Dependencies on other units (what they can assume exists)

Merge worktrees after all units complete and pass verification.

## Progress Tracking

- Log progress to cortex stream as implementation proceeds
- Update workflow state at phase transitions
- Workers report completion/blockers via channels

## Post-Implementation: Review + QA

After implementation is complete and tests pass, spawn two independent sessions before moving to close:

### Code Review Session

Spawn a fresh session to review the implementation. It must have NO context from the implementation — only the contracts, the diff, and the plan.

```
cortex session spawn \
  --name <task>-review \
  --repo <repo> \
  --worktree <task>-review \
  --goal "Code review for <task>"
```

Send the reviewer:
- Path to contracts file (success criteria + quality gates)
- The git diff or branch to review
- Path to plan file
- Instruction: "Review this implementation against the contracts. Check success criteria, quality gates, and code quality. Report findings."

The reviewer must be independent — do not review your own work.

### QA / Verification Session

Spawn a fresh session to verify the implementation against contracts. This is manual/integration verification, not just running tests.

```
cortex session spawn \
  --name <task>-qa \
  --repo <repo> \
  --worktree <task>-qa \
  --goal "QA verification for <task>"
```

Send the QA session:
- Path to contracts file
- The branch with implementation
- Instruction: "Verify each success criterion and quality gate in the contracts. Run verification commands. Check edge cases. Report pass/fail per criterion with evidence."

### Scope gating

- **Lightweight:** Self-review + run verification commands. No separate sessions needed.
- **Standard:** Spawn review session. QA can be self-verified or spawned based on complexity.
- **Deep:** Always spawn both review and QA sessions. They run in parallel.

Wait for review + QA results before moving to close. Fix any findings before shipping.

## Handling Blockers

When blocked during execution:
- Log the blocker to cortex stream
- If a worker is blocked: report via channels, controller decides next step
- If something contradicts the plan: stop, flag to user, don't improvise
- If a test can't be written for a step: flag it — don't skip testing

## What NOT to Do

- Do not implement without a worktree when working in a repo (per CLAUDE.md rules)
- Do not try to do deep-scope work inline — spawn workers
- Do not skip TDD steps even when "the fix is obvious"
- Do not improvise beyond the plan without flagging to the user
- Do not send workers raw memory — copy verified content into their prompt
