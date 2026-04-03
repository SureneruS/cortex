---
name: workflow
description: Use when starting any feature work, bug fix, or non-trivial implementation task. Orchestrates the align → plan → execute → close workflow.
---

# Workflow

Scope-adaptive feature-building workflow. Four phases, each with its own skill loaded on demand.

## Phases

1. **Align** — Load `cortex:workflow-align`. Build shared understanding, write contracts.
2. **Plan** — Load `cortex:workflow-plan`. Produce a plan artifact. Always TDD.
3. **Execute** — Load `cortex:workflow-execute`. Implement via cortex sessions.
4. **Close** — Load `cortex:workflow-close`. Repo health, ship, capture learnings.

## How It Works

Load the skill for your current phase. Each phase skill has full instructions.

Phases are independent — each self-assesses its depth (lightweight/standard/deep) using the global scope from contracts as input. The user can override scope at any time.

## Scope Levels

| Level | Signal | Ceremony |
|-------|--------|----------|
| **Lightweight** | 1-3 files, clear implementation | Short contracts, 50-line plan, inline execution |
| **Standard** | Multiple components, moderate complexity | Detailed contracts, full plan, dispatch dev agent |
| **Deep** | Ambiguous requirements, architectural decisions | Multiple exploration rounds, comprehensive plan, multiple workers |

## Skip Resilience

Any phase can be skipped. The workflow adapts:
- Skip align → plan asks for intent inline
- Skip plan → execute works from conversation context
- User says "skip to X" → go there immediately

## Rules

- **User decides.** Present facts and observations. Options only when asked, presented neutrally.
- **TDD always.** Tests before implementation at every scope.
- **Skepticism.** No doc is authoritative unless user says so. Memory can be stale. Confirm when something is off.
- **Cortex is undercover.** Never reference cortex in Linear, PRs, Slack, or external tools.
- **Contracts are truth.** Once agreed, the contracts file is the source of truth.

## Start

Load `cortex:workflow-align` and begin with the task at hand.
