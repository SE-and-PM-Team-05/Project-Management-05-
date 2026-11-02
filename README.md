# BizPartnerCheck

Team 05 · Software Engineering and Project Management · IMC Krems · Practical Projects 2026/27

BizPartnerCheck is a multi-tenant web service that automates the due-diligence checks an Austrian construction company must run before contracting a business partner (VAT number, fake-company list, HFU list, company register, business licenses) and stores every check as evidence.

- **Requirements:** SRS v2.1 (combined team version), kept in the team folder; changes follow REQ-CM-001
- **Backlog:** Jira project [SCRUM](https://sepmimc.atlassian.net/jira/software/projects/SCRUM/boards/1)
- **AI agent instructions:** [AGENTS.md](AGENTS.md)

## Status

The Django skeleton and CI are in place (**SCRUM-17**). Deployment is added once **SCRUM-42** chooses the host and database provider; until then the `deploy` job in CI is a placeholder.

## Run it locally

You need Python 3.14, PostgreSQL and git. On Ubuntu:

```bash
sudo apt install git python3-venv python3-pip postgresql
sudo -u postgres createuser --createdb "$USER"
createdb bizpartnercheck
```

One-time setup in the repository folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py create_superadmin you@example.com
```

`create_superadmin` prints a one-time password. Log in at http://localhost:8000/admin/ and choose a new one. The command refuses to run if a Super Admin already exists.

After that, one command starts the app:

```bash
python manage.py runserver
```

Before you push, run the same checks as CI:

```bash
ruff check . && ruff format --check . && pytest
```

Emails (verification links, password resets) are printed in the `runserver` terminal unless `EMAIL_HOST` is set.

### Environment variables

`settings.py` reads a local `.env` file if it exists; real environment variables take precedence. On the host, set them in its secret settings.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_DEBUG` | no | `false` | `true` only on your own machine. Off means HTTPS only, HSTS and secure cookies. |
| `DJANGO_SECRET_KEY` | when debug is off | dev key | Long random string; different per environment. |
| `DJANGO_ALLOWED_HOSTS` | when debug is off | – | Comma-separated domain names, e.g. `bizpartnercheck.example.com`. |
| `DATABASE_URL` | no | `postgres:///bizpartnercheck` | `postgres://user:password@host:port/name`. |
| `EMAIL_HOST` | no | – | SMTP server; if empty, emails go to the console. |
| `EMAIL_PORT` | no | `587` | SMTP port (STARTTLS). |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | with `EMAIL_HOST` | – | SMTP login. |
| `DEFAULT_FROM_EMAIL` | no | `BizPartnerCheck <noreply@localhost>` | Sender of outgoing emails. |
| `DJANGO_LOG_LEVEL` | no | `INFO` | Log level. |

### Dependencies

Direct dependencies are listed in `requirements.in` (app) and `requirements-dev.in` (tools); `requirements.txt` and `requirements-dev.txt` are the pinned lock files. To add or upgrade a library (agree on it in the team first):

```bash
pip-compile --strip-extras requirements.in
pip-compile --strip-extras requirements-dev.in
pip install -r requirements.txt -r requirements-dev.txt
```

### CI

Every push to `main` and every pull request runs `.github/workflows/ci.yml` against PostgreSQL 18: ruff, formatting, missing migrations, Django's deployment checks and pytest. Only a green build on `main` reaches the `deploy` job.

Reviews before merging are enforced by a branch protection rule on `main` (Settings → Branches): require a pull request with 1 approval and the `test` status check.

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
