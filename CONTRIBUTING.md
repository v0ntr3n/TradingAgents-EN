# Contributing Guide (CONTRIBUTING)

Thank you for your interest in TradingAgents-CN Community Edition! This project evolves continuously through a **community co-building** model, and contributions of all forms are welcome.

## Ways to Contribute

| Type | Examples |
|------|------|
| Bug Fixes | Fixing data fetching failures, UI glitches, or analysis pipeline errors |
| Documentation Improvements | Adding/correcting user manuals, study guides, or code comments |
| Data Source Adaptation | Integrating new public market/financial data APIs, or fixing upstream API changes |
| Feature Discussions | Proposing feature suggestions and usage feedback in Issues |

## Where to Start

Not sure where to begin? Look for opportunities in this order:

1. **Browse Issues labeled `good first issue`** — these are starter tasks specially prepared for newcomers
2. **Broken data source API bugs** — small in scope and easy to verify, ideal for a first PR
3. **Email us**: anonymous@example.com, describing your skills and areas of interest, and we will suggest suitable tasks

## PRs Are the Only Evaluation Criterion

We **do not review resumes or conduct interviews** — Pull Requests are the only way we evaluate contributors.

A high-quality PR typically has three characteristics:

1. **Solves a real problem**: Fixes an actual bug or fills a genuine gap, rather than making changes for the sake of changing
2. **Explains the rationale**: The PR description clearly explains "why the change was made", not just "what was changed"
3. **Responds to review feedback**: Actively addresses maintainers' review comments and follows up with revisions

Contributors who consistently submit high-quality PRs (over an evaluation period of ~3 months) have the opportunity to become **Core Collaborators**, participating in release planning and key module development. The expected time commitment for Core Collaborators is **1–2 hours of asynchronous communication per week** (no fixed online hours required), as we understand everyone has their own day job.

## What Contributors Get

The project currently generates a small amount of revenue (via user donations for points), which is **not yet sufficient to cover server and development token costs**. Therefore, we cannot pay financial compensation to contributors at this stage. Current rewards include:

- **Public Attribution & Visibility**: Named acknowledgments in release notes and official articles
- **Rare Engineering Experience**: Deep hands-on experience building production multi-agent systems (Agent orchestration, debate collaboration, capability extension)
- **Future Commercialization Priority**: Core contributors receive priority consideration when the project commercializes

### Revenue-Sharing Framework

We outline the principles of "how revenue will be shared once costs are covered" upfront so you know what to expect before investing your time:

| Stage | Revenue Status | Contributor Rewards |
|------|---------|-----------|
| Current | Modest revenue, not yet covering server and token costs | Attribution + Experience + Commercialization Priority |
| Cost Coverage | Revenue covers base costs with a surplus | Launch of a **Community Contribution Fund**, evaluated and distributed annually: Core Collaborators may receive consulting fees / project bonuses |
| Sustained Surplus | Stable commercialization | Contribution-based profit sharing or formal employment opportunities |

Three guiding principles:

1. **No promises of equity or fixed revenue-sharing percentages** — the project has not incorporated as a legal entity, and promising early equity carries legal risks
2. **Contributions are evaluated holistically by maintainers** — based on PR quality, impact, and consistency rather than mechanical formulas (lines of code or PR counts are poor metrics)
3. **The above are target principles rather than binding legal commitments** — they will be adjusted according to actual revenue; specific distribution plans will be formally announced upon entering the "Cost Coverage" stage

We do not promise early equity or fixed revenue shares.

## Contributor License Agreement (CLA)

After you submit your first PR, the maintainer will send you a Contributor License Agreement (CLA) to sign. Signing the CLA is a prerequisite for merging.

### Code Ownership After Merging

This is the question contributors care about most. The rules are as follows:

1. **You retain copyright**: The copyright of the code you submit always belongs to you, with the git commit history serving as the original record; you retain the right to use code you wrote in other contexts
2. **The project receives a perpetual license**: Through the CLA, you grant this project a perpetual, worldwide, royalty-free license to incorporate your contribution into the project and to use, modify, sublicense, and commercially distribute it under the project's licensing framework (including commercial licenses for proprietary components)
3. **Outbound licensing follows the project**: Merged code is licensed externally as part of the project as a whole (either under Apache-2.0 components or proprietary source-available components) rather than under individual contributor licenses; your attribution is preserved in the commit history and acknowledgments list

**Why a CLA is needed**: This project uses a hybrid license (partially open-source + partially proprietary/commercial). Without a CLA, contributor code merged into proprietary components would create legal obstacles to commercialization; with a CLA, the project can commercialize compliantly and sustainably to give back to the open-source community.

> Model note: Full copyright assignment is too aggressive toward contributors, while DCO (Signed-off-by) does not grant commercial licensing rights to the project. This project adopts the industry-standard CLA model (similar to the Apache Software Foundation and Google).

## PR Submission Workflow

1. **Fork and clone**: Fork this repository to your account and run `git clone <your_fork>`
2. **Create a branch**: Create a working branch from the main branch, named `fix/short-description` or `feat/short-description`
3. **Commit in small steps**: Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages (`fix: fix xxx` / `feat: add xxx` / `docs: document xxx`)
4. **Verify locally**: Run through the verification checklist below
5. **Open a PR**: Follow Conventional Commits for the PR title as well; the PR template will load automatically. Focus on explaining "why the change was made" and how it was verified in the description
6. **Respond to reviews**: Maintainers will review as soon as possible. Follow up with revisions based on feedback — response quality is part of the evaluation

## Development Environment

- Python 3.11 (see `requirements.txt` for backend dependencies)
- Node.js 18+ (see `frontend/package.json` for frontend dependencies)
- MongoDB and Redis (local or Docker)
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`)

Before submitting a PR, please ensure:

- [ ] Backend changes: `python -m py_compile <changed_files>` passes and `import app.main` succeeds
- [ ] Frontend changes: `npx vue-tsc --noEmit` and `npm run build` pass
- [ ] No new paid service dependencies or hardcoded secrets are introduced

## Compliance Red Lines

This project is positioned as a **research assistance tool**. Please ensure your contribution:

- Does not introduce trading instruction features such as target prices, stop-loss/take-profit levels, or buy/sell timing
- Does not remove or weaken compliance disclaimers such as "does not constitute investment advice"
- Does not scrape data sources that require login or payment, and does not bypass platform anti-scraping restrictions
- Does not introduce third-party dependencies under strong copyleft licenses such as GPL / AGPL — this project contains proprietary components and only accepts permissive dependencies (MIT / Apache-2.0 / BSD, etc.)

PRs that violate compliance red lines will not be merged.

## Code of Conduct

Be friendly and respectful in Issues, PRs, and discussions; focus on the issue rather than the person; helping newcomers is a plus.

## Communication Channels

- **Initial communication via email**: anonymous@example.com (collaboration intent, discussions outside PRs, commercial inquiries)
- **Specific technical issues**: Prefer public discussions in GitHub Issues / PRs so knowledge is preserved and accessible to future contributors
- **Deep collaboration**: Once collaboration goes smoothly, we will invite you to join the project **WeChat group** and **Knowledge Planet (Zsxq)** to participate in daily discussions and release planning
