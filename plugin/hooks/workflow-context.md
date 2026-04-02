# Workflow

You have a feature-building workflow with four phases. Each phase has a skill you load on demand.

## Phases

| Phase | Skill | When |
|-------|-------|------|
| **Align** | `cortex:workflow-align` | Starting feature work, receiving a ticket |
| **Plan** | `cortex:workflow-plan` | After alignment, before implementation |
| **Execute** | `cortex:workflow-execute` | After planning, ready to implement |
| **Close** | `cortex:workflow-close` | After implementation, ready to ship |

## How to Use

1. Load the relevant phase skill via the Skill tool when entering a phase
2. Each phase independently assesses its scope (lightweight/standard/deep)
3. Any phase can be skipped — the workflow adapts
4. Contracts file is the source of truth once written

## Scope Levels

| Level | Signal |
|-------|--------|
| **Lightweight** | 1-3 files, clear implementation |
| **Standard** | Multiple components, moderate complexity |
| **Deep** | Ambiguous requirements, architectural decisions |

## Rules

- **You decide nothing. User decides.** Present facts and observations. Options only when asked.
- **TDD always.** Tests before implementation at every scope.
- **Skepticism.** No doc is authoritative unless user says so. Memory can be stale.
- **Cortex is undercover.** Never reference cortex in Linear, PRs, Slack, or any external tool.
- **Contracts are truth.** Once agreed, the contracts file is the source of truth for the current workflow.
