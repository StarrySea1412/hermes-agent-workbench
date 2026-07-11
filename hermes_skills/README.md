# Hermes Skills

This directory stores project-local Hermes skill files.

## Current groups

- `agent-engineering/` for generic workbench skills
- `bid-writing/` for the bid workflow extension

## Skill format

Each skill is a Markdown file with frontmatter:

```markdown
---
name: skill-name
description: Short description
version: 1.0.0
author: Hermes Agent Workbench
tags: [agent, engineering]
---

# Skill Title

Skill instructions...
```

## How the workbench uses these files

- templates can point to a skill path through the `skill` field
- the backend loads the file and appends it to the runtime system prompt
- the Skills page lists discovered local skill files

## Generic examples

- `agent-engineering/general-operator`
- `agent-engineering/research-scout`
- `agent-engineering/artifact-builder`

## Domain-specific examples

- `bid-writing/tender-analyzer`
- `bid-writing/chapter-planner`
- `bid-writing/bid-chapter-writer`
- `bid-writing/compliance-reviewer`
