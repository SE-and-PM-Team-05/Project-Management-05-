# BizPartnerCheck

Team 05 · Software Engineering and Project Management · IMC Krems · Practical Projects 2026/27

BizPartnerCheck is a multi-tenant web service that automates the due-diligence checks an Austrian construction company must run before contracting a business partner (VAT number, fake-company list, HFU list, company register, business licenses) and stores every check as evidence.

- **Requirements:** SRS v2.1 (combined team version), kept in the team folder; changes follow REQ-CM-001
- **Backlog:** Jira project [SCRUM](https://sepmimc.atlassian.net/jira/software/projects/SCRUM/boards/1)
- **AI agent instructions:** [AGENTS.md](AGENTS.md)

## Status

The repository is being set up. The Django project, CI and deployment arrive with **SCRUM-17**; the host and database provider are chosen in **SCRUM-42**. Setup and run instructions will be added here by SCRUM-17.

## Tech stack

Python + Django (templates, built-in authentication, admin, translations, ORM), PostgreSQL, `requests` + `feedparser` for the data sources, pytest + ruff, GitHub Actions for CI and the daily sync trigger, one managed host in the EU.

Keep it minimal: add a library only when a requirement needs it, and agree on it in the team first.

## Team

| GitHub | Role |
|---|---|
| @Bohelor | Developer |
| @OrangeElias | Developer |
| @wsci557 | Developer |
| @Maryams2005 | Developer |
| @cheriambanattuantonia-beep | Developer |
| @bgoeschlberger | Lecturer / customer |

## How we work

### Jira keys everywhere
Every piece of work belongs to a Jira work item, and its key (e.g. `SCRUM-24`) appears in GitHub so Jira can show the branches, commits and pull requests in the work item's **Development** section.

| What | Rule | Example |
|---|---|---|
| Branch | `SCRUM-<n>-short-description`, lowercase, hyphens | `SCRUM-24-vat-check` |
| Commit message | Starts with the key, then what changed in the imperative | `SCRUM-24 Add VIES client with 8 s timeout` |
| Pull request title | Starts with the key | `SCRUM-24 Check VAT number and company name via the API` |

Work without a Jira key does not get merged. If something has no work item yet, create one first.

### Branches and pull requests
- One work item = one branch = one pull request.
- Nobody pushes directly to `main`. Every change goes through a pull request.
- A pull request needs **one approving review from another team member** and **green CI** (ruff + pytest) before it is merged.
- Keep pull requests small; a reviewer should be able to read one in under 30 minutes.
- In the pull request description, list the acceptance criteria from the Jira work item and tick off which ones are met.
- The author merges after approval and moves the Jira work item to Done only when the Definition of Done is met.

### Definition of Done
A work item is done when:
- [ ] All acceptance criteria in the Jira work item are met and can be shown in a demo
- [ ] Code is reviewed and approved by another team member
- [ ] CI is green: ruff passes and all tests pass
- [ ] New logic has tests; test coverage of the check logic stays at or above 70 %
- [ ] Every database query is scoped to the user's organization, with a test that a user of organization A gets 404 on organization B's data (REQ-FUNC-013)
- [ ] No secrets, API keys or personal data are committed
- [ ] Documentation (this README, AGENTS.md, API reference) is updated if behaviour or setup changed
- [ ] The Jira work item links to the merged pull request (via its key) and is moved to Done

### Secrets
Credentials (database URL, email account, data-source access) live only in environment variables and the host's secret settings. Never commit `.env` files or keys; if one is committed by mistake, tell the team immediately so it can be revoked.

## Working with AI coding agents

Team members may use AI coding agents (Claude Code, Codex, Copilot and others) to write code. So that every agent produces code in the same style and follows the same rules, the project's shared instructions live in **[AGENTS.md](AGENTS.md)** at the root of this repository.

- **Every agent must read AGENTS.md.** Most agents load it automatically. Claude Code reads `CLAUDE.md`, which in this repository only points to AGENTS.md, so there is one source of truth.
- **Change the rules in AGENTS.md, not in your own prompts.** If you find a convention missing, add it to AGENTS.md in a pull request so every teammate's agent picks it up.
- **You are responsible for what you merge.** Read and understand agent-written code before opening the pull request; you must be able to explain it in a review or at the sprint review.
- **Reviews stay human.** An agent may help review, but the approving review comes from a team member.
- **Security-sensitive code** (login, API tokens, tenant isolation, deletion) gets an especially careful human review.
- **Never give an agent secrets** such as passwords, tokens or the `.env` file contents.
