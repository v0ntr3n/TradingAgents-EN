# TradingAgents-CN Documentation Center

> This documentation system is structured across three tiers — "Product Evolution, Iteration, and Development" — to serve readers in different roles.
>
> **Current Version: v3.0** | [Version Management Guidelines](#version-management-guidelines)

## Documentation System Overview

| Tier | Directory | Target Audience | Description |
|------|------|---------|------|
| Product | [01-product](./01-product/) | Everyone | Product positioning, roadmap, release notes, version comparisons |
| User Guide | [02-user-guide](./02-user-guide/) | End Users | Installation, configuration, feature usage, advanced guides |
| Development | [03-development](./03-development/) | Developers | Architecture design, API documentation, developer guides, workflows |
| Operations | [04-operations](./04-operations/) | Operations / DevOps | Deployment, database administration, monitoring, troubleshooting |
| Design | [05-design](./05-design/) | Product / Architects | **Managed by version number**: v3.0/v4.0/v5.0 |
| Knowledge Base | [06-knowledge](./06-knowledge/) | All Members | Lessons learned, Bug Chronicles, compliance requirements |
| Courses | [07-courses](./07-courses/) | Users / Learners | Advanced trading courses (24 lessons) |
| Blog | [08-blog](./08-blog/) | Everyone | Technical blog posts, release announcements |
| Archive | [99-archive](./99-archive/) | Historical Reference | **Archived by version number**: v0.1.x/v1.0.x/v2.0/v2.1 |

## Quick Navigation

### Complete User Manuals

- [v3.0 Complete User Manual (Standard Edition)](./02-user-guide/user-manual-v3.0.md)
- [v3.0 JD Cloud Partner Edition User Manual](./02-user-guide/jdyun-user-manual-v3.0.md) ⭐ Dedicated for JD Cloud Edition users

### Getting Started for New Users
0. [v3.0 System Introduction (Technical Edition)](./01-product/v3.0-system-introduction.md)
   - [v3.0 System Introduction (WeChat Official Account Edition)](./01-product/v3.0-system-introduction-for-wechat.md)
1. [Quick Start](./02-user-guide/getting-started/quick-start.md)
2. [Installation Guide](./02-user-guide/getting-started/installation.md)
3. [Docker Installation & Usage Guide](./02-user-guide/getting-started/docker-installation-guide.md)
4. [Database Setup](./02-user-guide/getting-started/database-setup.md)
5. [LLM Configuration](./02-user-guide/configuration/llm-config.md)
6. [Data Source Configuration](./02-user-guide/configuration/config-guide.md)

### Feature Usage
- [Single-Stock Analysis](./02-user-guide/features/stock-analysis.md)
- [Paper Trading (Virtual Learning Environment)](./02-user-guide/features/paper-trading.md)
- [Portfolio Analysis](./02-user-guide/features/portfolio-analysis.md)
- [Scheduled Analysis](./02-user-guide/features/scheduled-analysis.md)
- [Report Export](./02-user-guide/features/report-export.md)

### Advanced Features
- [Agent Workshop](./02-user-guide/advanced/prompt-management.md)
- [Prompt Management](./02-user-guide/advanced/prompt-management.md)
- [QMT Integration](./02-user-guide/advanced/qmt-usage.md)

### For Developers
- [Development Environment Setup](./03-development/getting-started/setup.md)
- [Project Structure](./03-development/getting-started/project-structure.md)
- [System Architecture](./03-development/architecture/system-overview.md)
- [API Documentation](./03-development/api/)
- [Development Workflow](./03-development/workflow/development-workflow.md)
- [Branching Strategy](./03-development/workflow/branch-guide.md)
- [JD Cloud Integration Guide](./03-development/guides/jdyun-integration-guide.md) ⭐ Dedicated for JD Cloud engineers

### Operations & Deployment
- [Docker Deployment](./04-operations/deployment/docker-deployment-guide.md)
- [Windows Portable Edition](./04-operations/deployment/windows-portable.md)
- [Database Operations](./04-operations/database/)
- [Troubleshooting](./04-operations/troubleshooting/)

### Product Evolution (Managed by Version Number)
- **[v3.0 (Current Version)](./05-design/v3.0/)** - Design documents for the current release version
  - [JD Cloud Partner Edition Custom Design](./05-design/v3.0/jdyun-edition-design.md)
  - [JD Cloud Login Authentication Design](./05-design/v3.0/jdyun-auth-design.md)
  - [v3.6.0 Community Edition Open-Source Separation Plan](./05-design/v3.0/v3.6.0-community-edition-separation-plan.md)
  - [Valuation Model Excel Deliverable Design (Declarative Deliverable)](./05-design/v3.0/valuation-excel-deliverable-design.md)
  - [Smart Assistant Quality Architecture Refactoring Design (A11)](./05-design/v3.0/assistant-quality-architecture-refactor.md) ⭐ Unified quality gate / evidence set / route registry, ending the "fix-as-you-find" pattern
- **[v4.0 (Next Version)](./05-design/v4.0/)** - Next version planning
  - [Current State and Long-Term Vision Mapping (Baseline Document)](./05-design/v4.0/current-state-and-vision-mapping.md) ⭐ Three-tier architecture positioning, codebase inventory, target revision records (R1-R8), and unified four-swimlane roadmap
- **[v5.0 (Long-Term Vision)](./05-design/v5.0/)** - Long-term vision
- [Frontier Research](./05-design/research/) - Version-independent frontier exploration

## Version Management Guidelines

### Core Principle

**Design documents (`05-design`) and archived documents (`99-archive`) must use explicit version number directories**. Relative names such as `current`, `latest`, or `new` are strictly prohibited.

### `05-design` Version Directory Rules

```
05-design/
├── v3.0/              # Design documents for the current release series (v3.0.x)
├── v4.0/              # Next version planning
├── v5.0/              # Long-term vision
└── research/          # Frontier exploration (version-independent)
```

**Version Naming Rules**:
- Major version directories: `v3.0`, `v4.0`, `v5.0` (corresponding to `major` in `major.minor`)
- Minor and patch iterations under the same major version do not create new directories; update files directly within the existing major version directory
- For example, design documents for v3.0.1, v3.0.2, and v3.1.0 are all placed under `v3.0/`

### `99-archive` Version Directory Rules

```
99-archive/
├── v0.1.x/              # All documents from the v0.1.x era
├── v1.0.x/              # All documents from the v1.0.x era
├── v2.0/                # v2.0 design documents
├── v2.1/                # v2.1 design documents
├── deprecated-features/ # Deprecated features (cross-version)
└── historical-fixes/    # Historical fix records (cross-version)
```

### Version Iteration Workflow

When releasing a new major version (e.g., v3.0 → v4.0):

1. **Design Document Migration**:
   - `05-design/v3.0/` → `99-archive/v3.0/` (archive current version)
   - `05-design/v4.0/` → `05-design/v4.0/` (remains in place, becoming the new current version)
   - Create `05-design/v5.0/` (begin planning the subsequent version)

2. **Release Notes**:
   - Create `v4.0.0.md` under `01-product/release-notes/`

3. **Knowledge Retention**:
   - Consolidate major bugs from the release cycle into `06-knowledge/bug-chronicle/`

4. **Prohibited Actions**:
   - ❌ Do not use relative directory names like `current/`, `next/`, or `future/` under `05-design/`
   - ❌ Do not leave old-version documents unarchived inside `05-design/v3.0/`
   - ❌ Do not modify archived documents across versions (if modifications are needed, copy them into the current version's directory)

### Version Management Across Other Tiers

| Tier | Version Management Method | Description |
|------|-------------|------|
| 01-product | Versioned filenames | `release-notes/v3.0.0.md`, `comparison/v2.1-vs-v3.0.md` |
| 02-user-guide | Tracks current version | Content is updated alongside the current release; historical versions are not kept |
| 03-development | Tracks current version | Content is updated alongside the current release; historical versions are not kept |
| 04-operations | Tracks current version | Content is updated alongside the current release; historical versions are not kept |
| 05-design | **Versioned directories** | One directory per major version; archived upon version transition |
| 06-knowledge | Accumulated across versions | Organized by quarter or topic; not bound to a specific version |
| 99-archive | **Versioned directories** | One directory per major version |

## Document Naming Conventions

- Consistently use lowercase kebab-case (e.g., `quick-start.md`)
- Append version suffixes to version-specific files (e.g., `docker-deployment-v1.md`)
- Prefix temporary files with dates (e.g., `2025-10-26-bugfix.md`)

## ADR (Architecture Decision Records)

Key architectural decisions are recorded in [03-development/decisions/](./03-development/decisions/). Each ADR includes:
- Context: What problem is being faced
- Decision: Which solution was chosen
- Rationale: Why this solution was selected
- Consequences: What impacts result from the decision
