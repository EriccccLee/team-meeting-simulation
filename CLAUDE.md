# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

A **digital team member profile system** for the Nexon AI Context team. It stores structured knowledge bases derived from Slack message history, enabling AI agents to simulate team meetings, personalize colleague interactions, and power RAG/knowledge-graph systems.

This is a **data/knowledge repository** — no runnable code lives here.

## Team Member Profiles (`team-skills/`)

Each team member has a folder named by their Slack slug:

| Slug | Name | Role |
|------|------|------|
| `leecy` | 이창영3 | AI Context Team Coordinator/PM |
| `jasonjoe` | 조성훈 | Systems & Infrastructure Engineer (Snowflake, n8n, GCP) |
| `philgineer` | 윤준호 | Full-Stack AI Engineer (GCP Cloud Run, Neo4j, RAG) |
| `jmyeon` | 연준명 | Full-Stack AI Engineer (Slack bots, Knowledge Graphs, Vertex AI) |
| `rockmin` | 최석민 | AI/ML Pipeline Engineer (embeddings, clustering, tool evaluation) |

## File Conventions per Team Member

Every folder contains these files with specific roles:

- **`meta.json`** — Administrative metadata: slug, Slack UID, message count, version, timestamps. Update `updated_at` and increment `corrections_count` when making changes.
- **`SKILL.md`** — The canonical profile. Dual-part structure (see below). This is the source of truth.
- **`persona.md`** — Condensed personality summary, derived from SKILL.md Part B.
- **`work.md`** — Work responsibility summary, derived from SKILL.md Part A.
- **`slack_messages.json`** — Raw Slack messages used as training data. Do not edit.

## SKILL.md Architecture

Each `SKILL.md` follows a strict two-part structure:

**PART A — Technical Profile**
- Primary job responsibilities
- Technology stack (languages, tools, frameworks)
- Work processing style and philosophy
- Communication patterns at work

**PART B — Persona Layers**
- Layer 0: Absolute behavioral rules (non-negotiable, persona-breaking rules)
- Layer 1: Core identity and self-concept
- Layer 2: Expression style (speech patterns, writing quirks, vocabulary)
- Layer 3: Decision-making and problem-solving patterns
- Layer 4: Interpersonal relationship patterns
- Execution rules: how to apply the persona in simulation

Layer 0 rules must always be respected — they override other layers when there's a conflict.

## When Updating Profiles

1. Always edit `SKILL.md` as the source of truth first.
2. Sync relevant changes to `persona.md` (Part B summary) and `work.md` (Part A summary).
3. Bump `meta.json` → `updated_at` (ISO 8601) and increment `corrections_count`.
4. Do not modify `slack_messages.json` — it's raw source data.

## Adding a New Team Member

Create a new folder under `team-skills/<slug>/` with all five files. Use an existing member's files as the template. The `meta.json` `version` field starts at `"v1"`.

## Tech Stack Context (for profile accuracy)

The team works with: GCP (Cloud Run, GCS, Vertex AI), Snowflake, Neo4j, n8n, Claude/Gemini/Qwen LLMs, Slack API, Notion API, MS Graph API, Docker, Python, JavaScript/Node.js, RAG systems, knowledge graphs.
