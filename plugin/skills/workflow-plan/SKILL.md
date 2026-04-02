---
name: workflow-plan
description: Use when contracts exist and you need to produce an implementation plan — after alignment, before execution. Scales depth with scope. Always TDD.
---

# Plan

Produce a plan artifact that any session — including one with zero prior context — can execute from.

## Inputs

- Contracts file (from align phase)
- Codebase exploration (primary evidence — explore before planning)
- Cortex memory (queried for patterns/gotchas in the relevant area — flagged as potentially stale)

## Scope Self-Assessment

Each plan independently assesses its depth, using the global scope from contracts as input. The user can override.

| Level | Plan depth |
|-------|-----------|
| **Lightweight** | ~50 lines. Files, steps, test commands. One page. |
| **Standard** | Detailed file structure, test scenarios per component, dependencies, ordering. |
| **Deep** | Research phase first. Architecture decisions documented. Multiple implementation units with independent verification. |

## Always TDD

Every plan follows the red-green cycle. No exceptions, no scope exemptions.

For each implementation step:
1. Write failing test
2. Run it — verify it fails (red)
3. Write minimal implementation to pass
4. Run it — verify it passes (green)
5. Refactor if needed

The plan must show this ordering explicitly. Tests come before implementation in every step.

## Plan Structure

```markdown
# Plan: <task title>

**Contracts:** <path to contracts file>
**Scope:** lightweight | standard | deep

## Files
- Create: `exact/path/to/new_file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/test_file.py`

## Steps

### Step 1: <what>
**Test:** Write test for <behavior>
**Verify red:** `pytest tests/path/test_file.py::test_name -v` → expect FAIL
**Implement:** <what to change>
**Verify green:** `pytest tests/path/test_file.py::test_name -v` → expect PASS

### Step 2: <what>
...

## Verification
<inherited from contracts — commands to prove the full feature works>
```

### Scaling the Plan

**Lightweight:** Steps can be brief. A 50-line plan with file paths, test-first steps, and verification commands is enough.

**Standard:** Each step has explicit test code snippets, expected outputs, and file-level detail. Include dependency ordering.

**Deep:** Split into implementation units. Each unit is independently verifiable and can be assigned to a separate worker session. Include research findings and architecture decisions.

## Linear Sub-tickets

When splitting a feature into smaller units during planning:
- Create issues using the Linear template from the align skill
- Link to parent feature ticket
- Suggest acceptance criteria, priority, labels — wait for user approval
- Never reference cortex in Linear content

## Source Skepticism

- Codebase exploration is primary evidence for how things work today
- Docs, memory, and external references are hints — they may be outdated
- Confirm with user when something seems off or contradicts expectations

## Verification Gate (medium+ scope)

For standard and deep scope, an external verification agent checks:
- Plan covers all contract success criteria
- No contract items are unaddressed
- Test strategy covers each success criterion
- TDD ordering is correct (tests before implementation in every step)

## What NOT to Do

- Do not skip the plan. Lightweight scope gets a short plan, not no plan.
- Do not write steps without exact file paths.
- Do not put implementation before tests in any step.
- Do not write vague steps ("add error handling", "implement the feature").
- Do not assume docs are current — verify against the codebase.
