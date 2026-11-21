# BizPartnerCheck

Team 05 · Software Engineering and Project Management · IMC Krems · Practical Projects 2026/27

BizPartnerCheck is a multi-tenant web service that automates the due-diligence checks an Austrian construction company must run before contracting a business partner (VAT number, fake-company list, HFU list, company register, business licenses) and stores every check as evidence.

- **Requirements:** [SRS v2.9](docs/SRS.md) (combined team version); changes follow REQ-CM-001 and are recorded in its Revision History
- **Backlog:** Jira project [SCRUM](https://sepmimc.atlassian.net/jira/software/projects/SCRUM/boards/1)
- **AI agent instructions:** [AGENTS.md](AGENTS.md)

## Status

The Django skeleton and CI are in place (**SCRUM-17**). The app is deployed to **Render**, with the database on **Neon** and email through **Brevo** (decided in **SCRUM-42**); see [Deployment](#deployment) for the one-time setup.

<<<<<<< Updated upstream
Organizations can register (**SCRUM-21**), and `POST /api/v1/checks` checks a VAT number and company name against VIES (**SCRUM-24**, see [API](#api)). Users create, list and revoke API tokens on the **API tokens** page (`/tokens/`) or through `/api/v1/tokens` (**SCRUM-72**), and every API call can authenticate with one as a Bearer token (**SCRUM-71**), limited to 200 calls per minute per token (**SCRUM-73**).
=======
Organizations can register (**SCRUM-21**), and `POST /api/v1/checks` checks a partner by its VAT number, optionally with its company name (**SCRUM-24**, **SCRUM-93**, see [API](#api)). Users create, list and revoke API tokens on the **API tokens** page (`/tokens/`) or through `/api/v1/tokens` (**SCRUM-72**), and every API call can authenticate with one as a Bearer token (**SCRUM-71**), limited to 200 calls per minute per token (**SCRUM-73**).
>>>>>>> Stashed changes

## Run it locally

You need Python 3.14, PostgreSQL and git.

### Ubuntu

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
python manage.py createcachetable
python manage.py create_superadmin you@example.com
```

### Windows

1. Install Python 3.14 and git in PowerShell:
   ```powershell
   winget install --id Python.Python.3.14 --exact
   winget install --id Git.Git --exact
   ```
2. Install PostgreSQL 18 with the installer from https://www.postgresql.org/download/windows/ (winget's download is often refused by the installer's server). Choose a password for the `postgres` user and remember it; keep port 5432 and the other defaults; Stack Builder isn't needed.
3. Create the database; it asks for the `postgres` password:
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres bizpartnercheck
   ```
4. Allow PowerShell to run the virtual environment's activation script (once per Windows account):
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

One-time setup in the repository folder:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

Open `.env` and change the `DATABASE_URL` line to use your `postgres` password (Windows PostgreSQL needs a password, unlike the Ubuntu setup):

```
DATABASE_URL=postgres://postgres:YOUR_PASSWORD@localhost:5432/bizpartnercheck
```

If the password contains `%`, `@`, `:`, `/` or `#`, write them as `%25`, `%40`, `%3A`, `%2F` and `%23`. Then:

```powershell
python manage.py migrate
python manage.py createcachetable
python manage.py create_superadmin you@example.com
```

In every new terminal, run `.venv\Scripts\Activate.ps1` in the repository folder first. The commands below work on both systems, except that Windows PowerShell 5 doesn't understand `&&`: run the CI checks there as `ruff check .; ruff format --check .; pytest`.

### Both systems

`createcachetable` creates the table Django's cache lives in; the failed-login counter needs it. Run it once per database; on Render, `build.sh` does it on every deploy.

`create_superadmin` prints a one-time password. Log in at http://localhost:8000/admin/ and choose a new one. The command refuses to run if a Super Admin already exists.

After that, one command starts the app:

```bash
python manage.py runserver
```

Before you push, run the same checks as CI:

```bash
ruff check . && ruff format --check . && pytest
```

Emails sent by the app (invitations) are printed in the `runserver` terminal unless `EMAIL_HOST` is set.

Login: users log in through Keycloak (see [Keycloak](#keycloak) below), so you need a Keycloak running to log in as anyone but the Super Admin. The Super Admin logs in with a password at `/admin/`, which is locked for 15 minutes after 5 failed attempts. A session ends after 8 hours without activity.

### Keycloak

Keycloak owns user accounts: sign-up, passwords, email verification, password reset and lockout. The app talks to it through OpenID Connect (`mozilla-django-oidc`) and creates its own user record, matched by email address, on the first login. A new user then registers an organization or opens an invitation link. Only accounts whose email Keycloak has verified can log in; staff accounts (the Super Admin) can't log in through Keycloak, only at `/admin/`.

The realm is set up from [`keycloak/bizpartnercheck-realm.json`](keycloak/bizpartnercheck-realm.json) on Keycloak's first start: user registration with email verification, password reset, a minimum password length of 8, lockout for 15 minutes after 5 failed logins (REQ-SEC-004), and the `bizpartnercheck` client. The file reads two environment variables, which must be set before the first start: `APP_URL` (the app's address without a trailing slash) and `KEYCLOAK_CLIENT_SECRET` (the same value as in the app's `.env`). Once the realm exists, Keycloak skips the import, so later changes are made in its admin console.

Run Keycloak locally in development mode, with Docker (in this folder; in PowerShell replace `$(pwd)` with `${PWD}`):

```bash
docker run -p 8080:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin -e APP_URL=http://localhost:8000 -e KEYCLOAK_CLIENT_SECRET=local-dev-secret -v "$(pwd)/keycloak:/opt/keycloak/data/import" quay.io/keycloak/keycloak:26.4 start-dev --import-realm
```

or without Docker: install Java 21, download and unpack the Keycloak 26.4 zip from https://www.keycloak.org/downloads, copy `keycloak/bizpartnercheck-realm.json` into its `data/import` folder, set the same four environment variables and run `bin/kc.sh start-dev --import-realm` (`bin\kc.bat` on Windows).

Then put `KEYCLOAK_CLIENT_SECRET=local-dev-secret` in your `.env`. Locally there's no email server, so Keycloak can't send verification emails: create test users at http://localhost:8080/admin/ (log in as `admin` / `admin`, switch to the `bizpartnercheck` realm, Users → Add user, switch on *Email verified*, then set a password on the Credentials tab).

### Environment variables

`settings.py` reads a local `.env` file if it exists; real environment variables take precedence. On the host, set them in its secret settings.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_DEBUG` | no | `false` | `true` only on your own machine. Off means HTTPS only, HSTS and secure cookies. |
| `DJANGO_SECRET_KEY` | when debug is off | dev key | Long random string; different per environment. |
| `DJANGO_ALLOWED_HOSTS` | when debug is off | – | Comma-separated domain names, e.g. `bizpartnercheck.example.com`. |
| `DATABASE_URL` | no | `postgres:///bizpartnercheck` | `postgres://user:password@host:port/name`; options such as Neon's `?sslmode=require` are passed to PostgreSQL. |
| `EMAIL_HOST` | no | – | SMTP server; if empty, emails go to the console. |
| `EMAIL_PORT` | no | `587` | SMTP port (STARTTLS). |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | with `EMAIL_HOST` | – | SMTP login. |
| `DEFAULT_FROM_EMAIL` | no | `BizPartnerCheck <noreply@localhost>` | Sender of outgoing emails. |
| `DJANGO_LOG_LEVEL` | no | `INFO` | Log level. |
| `KEYCLOAK_REALM_URL` | no | `http://localhost:8080/realms/bizpartnercheck` | The Keycloak realm users log in through. |
| `KEYCLOAK_CLIENT_ID` | no | `bizpartnercheck` | Client ID of the app in that realm. |
| `KEYCLOAK_CLIENT_SECRET` | when debug is off | – | Secret of the `bizpartnercheck` client; the same value Keycloak got as `KEYCLOAK_CLIENT_SECRET` when it imported the realm. |

### Test names and SRS requirement IDs

SRS Section 4 asks for one verification record per requirement. In this repository the tests are those records, so every test says which requirement it verifies (SCRUM-55):

- Put the requirement ID(s), written exactly as in the SRS (`REQ-SEC-004`), at the start of the test's docstring. If one test verifies several requirements, list them all, separated by commas.
- A test function whose name carries the ID (`test_req_func_031_...`) still needs the ID in its docstring, because a search for `REQ-FUNC-031` does not match the lower-case name.

```python
def test_lock_ends_after_15_minutes(client, admin, monkeypatch):
    """REQ-SEC-004: a locked account can log in again after 15 minutes."""
```

To see which tests verify a requirement, search the tests for its ID. A search with no hit means no test verifies it yet:

```bash
grep -rn "REQ-SEC-004" tests/
```

In PowerShell: `Select-String -Path tests\*.py -Pattern "REQ-SEC-004"`.

To list every requirement ID from the SRS that no test mentions (many are verified by inspection, demonstration or analysis, not by a test), in Ubuntu or Git Bash:

```bash
grep -o "REQ-[A-Z]*-[0-9]*" docs/SRS.md | sort -u | while read id; do grep -rqF "$id" tests/ || echo "$id"; done
```

`tests/test_traceability.py` runs in CI and fails if a test names no requirement ID or names one that does not exist in `docs/SRS.md`.

### Dependencies

Direct dependencies are listed in `requirements.in` (app) and `requirements-dev.in` (tools); `requirements.txt` and `requirements-dev.txt` are the pinned lock files. To add or upgrade a library (agree on it in the team first):

```bash
pip-compile --strip-extras requirements.in
pip-compile --strip-extras requirements-dev.in
pip install -r requirements.txt -r requirements-dev.txt
```

### CI

Every push to `main` and every pull request runs `.github/workflows/ci.yml` against PostgreSQL 18: ruff, formatting, missing migrations, Django's deployment checks and pytest. Only a green build on `main` reaches the `deploy` job, which triggers a deploy on Render.

Reviews before merging are enforced by a branch protection rule on `main` (Settings → Branches): require a pull request with 1 approval and the `test` status check.

## Deployment

Production runs on **Render** (app, Frankfurt), **Neon** (PostgreSQL, EU) and **Brevo** (SMTP email). The free tiers are enough for the course. Render's free web service sleeps when nobody uses it and takes a while to wake up, so open the site a minute before a demo.

A push to `main` deploys only after CI is green: the `deploy` job in `.github/workflows/ci.yml` calls Render's deploy hook, and Render's own auto-deploy is switched off. On each deploy Render runs `build.sh` (install, `collectstatic`, `migrate`, `createcachetable`) and then starts gunicorn.

### One-time setup

1. **Neon:** create a project in an EU region (e.g. AWS Europe Central, Frankfurt) and copy its connection string. It looks like `postgresql://user:password@ep-….eu-central-1.aws.neon.tech/neondb?sslmode=require`. Both the pooled (`-pooler` in the host) and the direct connection string work: the settings check reused connections and switch off server-side cursors, which Neon's pooler doesn't support.
2. **Brevo:** create an account, verify the sender address (best on a domain the team owns, with Brevo's SPF and DKIM records; mail "from" a Gmail address tends to land in spam) and create an **SMTP key** (Settings → SMTP & API). Note the SMTP login shown there.
3. **Render:** New → Web Service → connect this GitHub repository (an organization owner must allow Render's GitHub app for `SE-and-PM-Team-05`), then:

   | Setting | Value |
   |---|---|
   | Branch | `main` |
   | Region | Frankfurt (EU Central) |
   | Runtime | Python |
   | Build Command | `bash build.sh` |
   | Start Command | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT` |
   | Instance Type | Free |
   | Health Check Path | `/healthz` |
   | Auto-Deploy | Off (CI triggers deploys) |

   Environment variables (Render → Environment). Never commit these values:

   | Variable | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | A new random string, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `DJANGO_ALLOWED_HOSTS` | Only needed for an own domain; Render's `onrender.com` address is added automatically from `RENDER_EXTERNAL_HOSTNAME` |
   | `DATABASE_URL` | The Neon connection string from step 1 |
   | `EMAIL_HOST` | `smtp-relay.brevo.com` |
   | `EMAIL_PORT` | `2525` (Render's free plan blocks outgoing traffic on 587; with 587 registration hangs and fails with a 500) |
   | `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | The Brevo SMTP login and SMTP key from step 2 |
   | `DEFAULT_FROM_EMAIL` | The verified sender, e.g. `BizPartnerCheck <noreply@your-domain>` |
   | `KEYCLOAK_REALM_URL` | `https://<your-keycloak-service>.onrender.com/realms/bizpartnercheck` (step 7) |
   | `KEYCLOAK_CLIENT_SECRET` | The same random string as in the Keycloak service (step 7). Without it the app refuses to start. |

   Render reads the Python version from `.python-version`; if the build log shows a different version, also set `PYTHON_VERSION` to the full 3.14 version.
4. **Deploy hook:** Render → the service → Settings → Deploy Hook → copy the URL. In GitHub: repository Settings → Secrets and variables → Actions → New repository secret named `RENDER_DEPLOY_HOOK_URL` with that URL. Without it the `deploy` job only prints a warning.
5. **First deploy:** Render → Manual Deploy → Deploy latest commit (later deploys happen automatically after green CI on `main`). Then open `https://<your-service>.onrender.com/healthz`; it should answer `ok`.
6. **Super Admin:** the free plan has no shell on the server, so create the Super Admin from your own machine against the Neon database. In a terminal in this folder with `.venv` active, set `DATABASE_URL` to the Neon connection string for that terminal only, run `python manage.py create_superadmin you@example.com`, and log in at `https://<your-service>.onrender.com/admin/` with the one-time password it prints.
7. **Keycloak** (SCRUM-76): a second Render web service built from `keycloak/Dockerfile`, with its own database in the same Neon project.
   1. **Neon:** in the project from step 1, create a database named `keycloak` (Databases → New database). Use the **direct** connection (not `-pooler`): Keycloak keeps its own connection pool and doesn't work behind Neon's PgBouncer. Take host, user and password from the direct connection string.
   2. **Client secret:** create one random string, e.g. with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. It goes into both services as `KEYCLOAK_CLIENT_SECRET`.
   3. **Render:** New → Web Service → this repository, then:

      | Setting | Value |
      |---|---|
      | Name | e.g. `bizpartnercheck-auth`; the address becomes `https://<name>.onrender.com` |
      | Language | Docker |
      | Branch | `main` |
      | Root Directory | `keycloak` |
      | Region | Frankfurt (EU Central) |
      | Health Check Path | `/realms/bizpartnercheck` |
      | Auto-Deploy | Off: Keycloak only needs a deploy when its files change; use Manual Deploy then |

      Environment variables:

      | Variable | Value |
      |---|---|
      | `PORT` | `8080` (the port Keycloak listens on) |
      | `KC_HOSTNAME` | `https://<name>.onrender.com` |
      | `KC_DB_URL` | `jdbc:postgresql://<direct Neon host>/keycloak?sslmode=require` |
      | `KC_DB_USERNAME` / `KC_DB_PASSWORD` | User and password from the Neon connection string |
      | `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD` | A temporary admin login for the first start; replace it with a permanent admin in the admin console afterwards and remove these two variables |
      | `APP_URL` | `https://<your-service>.onrender.com` (the app from step 3, no trailing slash) |
      | `KEYCLOAK_CLIENT_SECRET` | The string from step 7.2 |

      **Instance type:** Keycloak is a Java server and needs more memory than the app. Render's free instance has 512 MB and sleeps when idle, which makes Keycloak slow to start or fail to start; if the free instance doesn't stay up, use a paid instance with more memory (team decision, SRS OD-10).
   4. **Deploy**, then open `https://<name>.onrender.com/admin/`, log in with the bootstrap admin and switch to the `bizpartnercheck` realm. Under **Realm settings → Email**, enter the Brevo SMTP settings from step 2 (host `smtp-relay.brevo.com`, port `2525`, StartTLS on, the SMTP login and key, and the verified sender as *From*), so Keycloak can send verification and password reset emails.
   5. **App:** in the app service from step 3, set `KEYCLOAK_REALM_URL` and `KEYCLOAK_CLIENT_SECRET` (table above) and deploy it. Test it: open the app, click Register, sign up, open the verification email, and register an organization.
8. **Daily BMF sync** (SCRUM-64): in GitHub, add a repository secret named `DATABASE_URL` with the Neon connection string from step 1 (Settings → Secrets and variables → Actions). Deploy the app first (step 5), so its migrations, including `checks.0002` with the fake-company list and the sync log, are applied on Neon: without those tables the sync crashes before it can write a sync log row. Then start the first import by hand: Actions → **Daily BMF sync** → Run workflow, and check that the run is green and `/admin/` → Sync logs shows a `success` row. Until it has run once, the fake-company check answers `UNKNOWN`.

### Daily BMF sync

`.github/workflows/sync-bmf.yml` runs `python manage.py sync_bmf` every day at 03:17 UTC, straight against the Neon database (REQ-FUNC-070). The job downloads the BMF list of sham companies, replaces the stored list in one transaction and writes one row to the sync log, which the Super Admin sees under `/admin/` → Sync logs (REQ-FUNC-072).

- **A failed run** (BMF unreachable, a changed page layout, a list less than half as long as the last one) changes nothing: checks keep using the last good copy, the sync log gets a `failed` row with the reason, and the run turns red in GitHub Actions. GitHub emails a failed scheduled run to whoever last changed the workflow's `cron` line. After 48 h without a successful run, fake-company results carry `stale: true` (REQ-FUNC-073).
- **A much shorter list** is rejected on purpose, because it usually means a broken download. If BMF really did shorten the list, run `python manage.py sync_bmf --allow-shrink` once from your own machine against the Neon database, as in step 6.
- **Settings:** the job sets placeholder values for `DJANGO_SECRET_KEY` and `KEYCLOAK_CLIENT_SECRET`, because `config/settings.py` refuses to load without them when debug is off; the import serves no web requests and logs nobody in. If a later change makes another setting required, add a placeholder to `sync-bmf.yml` too: `tests/test_sync_workflow.py` loads the settings with exactly the workflow's variables and fails otherwise.
- **Locally**, `python manage.py sync_bmf` fills your own database with the real list.
- GitHub only runs scheduled workflows from `main`, and it pauses them after 60 days without a commit in a public repository. Re-enable the workflow under Actions if that happens.

## API

All endpoints live under `/api/v1/` and answer in JSON. Times are UTC in ISO 8601.

### Authentication

Every endpoint needs an API token or a logged-in web session (REQ-INT-011).

- **API token (for your software):** create one on the **API tokens** page (`/tokens/`) and send it in every call as `Authorization: Bearer <token>`. No CSRF token and no cookies are needed. The call runs as the token's owner, with the owner's roles at the moment of the call (REQ-FUNC-021): a token of a user without the Request User role gets 403 on `POST /api/v1/checks`, and removing a role takes effect on the next call.
- **Web session (for trying things in the browser):** log in and send the CSRF token in the `X-CSRFToken` header for `POST` and `DELETE`.

The token is checked against the database on every call, so a revoked or expired token, or a token of a deactivated or deleted user, gets **401 `INVALID_TOKEN`** on the very next call (REQ-FUNC-023 asks for 60 s). The answer is the same for every reason, with the header `WWW-Authenticate: Bearer error="invalid_token"`. If the `Authorization` header is sent, it alone decides: a bad token is 401 even if the caller is also logged in. Tokens work only under `/api/`; they never log anybody into the web pages. The first 8 characters shown in the token list are not enough to authenticate.

```bash
curl -X POST https://<your-service>.onrender.com/api/v1/checks \
  -H "Authorization: Bearer $BPC_TOKEN" -H "Content-Type: application/json" \
  -d '{"vatNumber": "ATU12345678", "companyName": "Muster Bau GmbH"}'
```

### Rate limit

Each token may make **200 requests per minute** (REQ-SEC-003), counted over all endpoints. The minute starts with the first call after the previous minute ended. It is a fixed window, as the SRS describes it: a client can make 200 calls at the end of one window and 200 more right at the start of the next. Every answer to a token call carries the remaining quota:

| Header | Meaning |
|---|---|
| `X-RateLimit-Limit` | `200` |
| `X-RateLimit-Remaining` | Calls left in the current minute |
| `X-RateLimit-Reset` | Seconds until the current minute ends |

The 201st call within the minute gets **429 `RATE_LIMIT_EXCEEDED`** with `Retry-After` (seconds). It is rejected before anything else happens: no check runs and nothing is stored (UC-04, 2b). Rejected calls don't count, so waiting `Retry-After` seconds is always enough. The limit is per token, not per user: a second token has its own 200. Web-session calls have no per-token limit.

The count is kept on the token's database row and changed under a row lock, so it is exact even when several app processes serve the same token.

### `POST /api/v1/checks` – check a business partner

Runs the checks implemented so far, `vatValid` and `nameMatchesVat`, both answered by one call to VIES (REQ-FUNC-030…032). The other checks (fake-company list, HFU, Firmenbuch, GISA) are added in later sprints and are not in the response yet. Every accepted request is **stored** as evidence, atomically with all its results (REQ-REL-004); `requestId` is its ID. Stored requests cannot be changed, only deleted as a whole (REQ-FUNC-051): `save()`, `QuerySet.update()` and `bulk_update()` refuse, and there is no admin page or API route that edits them. Partners are never re-checked automatically, not after a sync and not over time; a re-check is a new request (REQ-FUNC-040, REQ-FUNC-041). Invalid or rejected calls store nothing.

**Authentication:** an API token or web session (see [Authentication](#authentication)) of a user with the Request User role. With a token, `requestedBy.tokenName` in the answer and in the stored request is the token's name (never its value); with a web session it is `null`.

Request body:

| Field | Required | Example | Notes |
|---|---|---|---|
| `vatNumber` | yes | `"ATU 123 456 78"` | Any EU VAT number with its country prefix (Greece: `EL`). Spaces, dots and dashes are removed, letters upper-cased, then the format is checked per country (`accounts/validators.py`). |
| `companyName` | no | `"Muster Bau GmbH"` | If given, compared with the name registered in VIES. If left out (or blank), `nameMatchesVat` is `NOT_APPLICABLE` but still reports the registered name in `details.registeredName`, and the fake-company check matches by VAT number and FN only (**SCRUM-93**). |
| `companyRegisterNumber` | no | `"123456a"` | Austrian FN: up to 6 digits and a check letter. |
| `address`, `reference` | no | `"PO-4711"` | Free text; `reference` is your own reference and is echoed back. |
| `requiredLicenseCodes` | no | `["…"]` | List of strings; used once the GISA check exists. |

Response (shortened):

```json
{
  "requestId": "c1f0a7e2-5d1b-4b7e-9a10-3e2f6b8d9c41",
  "receivedAt": "2026-11-02T09:42:09Z",
  "completedAt": "2026-11-02T09:42:10Z",
  "organization": "Beispiel Bau GmbH",
  "requestedBy": { "user": "Anna Beispiel", "channel": "api", "tokenName": null },
  "partner": { "companyName": "Muster Bau GmbH", "vatNumber": "ATU12345678" },
  "checks": [
    { "check": "vatValid", "result": "TRUE", "source": "VIES", "dataTimestamp": "2026-11-02T09:42:09Z",
      "details": { "registeredAddress": "HAUPTSTRASSE 1, 3500 KREMS" } },
    { "check": "nameMatchesVat", "result": "TRUE", "source": "VIES", "dataTimestamp": "2026-11-02T09:42:09Z",
      "details": { "registeredName": "MUSTER BAU GMBH" } }
  ],
  "disclaimer": "Informational only; …"
}
```

`partner` echoes the optional fields only when they were sent, so a check with only a VAT number answers with `"partner": { "vatNumber": "ATU12345678" }`.

Each `result` is `TRUE`, `FALSE`, `UNKNOWN` (with `reason`: `SOURCE_UNAVAILABLE` or `NO_DETAILS_FOUND`) or `NOT_APPLICABLE`. `UNKNOWN` is never a pass or a fail. If VIES is down, the call still returns **200** with both checks `UNKNOWN / SOURCE_UNAVAILABLE`; VIES gets at most 8 s including one retry.

Errors return `{"error": {"code": "…", "message": "…", "fields": {…}}}`:

| Status | `code` | When |
|---|---|---|
| 400 | `INVALID_INPUT` | Missing or malformed field; `fields` names each one. VIES is not called. |
| 400 | `INVALID_JSON` | Body is not JSON. |
| 401 | `NOT_AUTHENTICATED` | No `Authorization` header and not logged in. |
| 401 | `INVALID_TOKEN` | The Bearer token is unknown, revoked or expired, its owner is deactivated, or the header is not `Bearer <token>`. |
| 403 | `PERMISSION_DENIED` | User lacks the Request User role. |
| 403 | `CSRF_FAILED` | Session call without `X-CSRFToken` header. |
| 405 | `METHOD_NOT_ALLOWED` | Anything other than POST. |
| 429 | `RATE_LIMIT_EXCEEDED` | More than 200 calls in a minute with this token; see [Rate limit](#rate-limit). Nothing is stored. |
| 500 | `INTERNAL_ERROR` | Unexpected error on our side, e.g. the request could not be stored; nothing is stored then. Details only in the server log. |

**Try it locally:** log in at http://localhost:8000/ (through Keycloak) with a Request User, open the browser console on that page and run:

```js
fetch("/api/v1/checks", {
  method: "POST",
  headers: { "Content-Type": "application/json",
             "X-CSRFToken": document.cookie.match(/csrftoken=([^;]+)/)[1] },
  body: JSON.stringify({ vatNumber: "ATU 123 456 78", companyName: "Muster Bau GmbH" }),
}).then(r => r.json()).then(console.log);
```

This calls the real VIES service. The tests never do; they mock VIES. How VIES is used is documented in [docs/sources/vies.md](docs/sources/vies.md).

### `/api/v1/tokens` – manage API tokens

Every user of an organization manages their own tokens; an Org Admin manages all tokens of the organization (SRS Appendix A, REQ-FUNC-020…023). The same rules apply on the web page `/tokens/`. Authentication as described in [Authentication](#authentication). With a Bearer token you can list tokens and revoke them (a token can revoke itself), but not create new ones (`403 PERMISSION_DENIED`): otherwise a leaked token could create replacements that keep working after it is revoked.

| Call | Body | Answer |
|---|---|---|
| `GET /api/v1/tokens` | – | 200 `{"tokens": [...]}`, newest first, revoked ones included |
| `POST /api/v1/tokens` | `name` (required, ≤ 100 characters), `userId` (optional, Org Admin only), `expiresAt` (optional: a date means the end of that day, Vienna time; or an ISO 8601 date and time) | 201 with the token **and its full value in `token`** |
| `DELETE /api/v1/tokens/{id}` | – | 204; revoking twice is harmless |

```json
{
  "id": 7, "name": "ERP prod", "prefix": "bpc_q3V9",
  "owner": { "id": 4, "email": "anna@beispielbau.at", "name": "Anna Beispiel" },
  "createdAt": "2026-11-16T09:00:00Z", "lastUsedAt": null, "expiresAt": null, "revokedAt": null,
  "active": true,
  "token": "bpc_q3V9xL0a…"
}
```

- The value starts with `bpc_`, so secret scanners can recognise a leaked token, followed by 320 random bits (still 300 after the visible first 8 characters); it is stored only as a SHA-256 hash (REQ-SEC-002). `token` appears **only in the `POST` answer**; afterwards no page or response shows more than the first 8 characters (`prefix`, REQ-FUNC-022).
- Tokens never expire unless `expiresAt` is set; it must lie in the future and in 2100 or earlier. Revoking is final.
- Deactivating a user revokes all their tokens; reactivating does not bring them back. Deleting a user deletes their tokens (REQ-FUNC-023).
- Errors use the same format and codes as `/api/v1/checks` (including 401 `INVALID_TOKEN` and 429), plus `404 NOT_FOUND` for a token of another user (unless you are Org Admin) or of another organization (REQ-FUNC-013). Creating a token for another user without the Org Admin role is `403 PERMISSION_DENIED`; the Super Admin has no organization and gets 403.

### Adding a data source

Each source (VIES, BMF, HFU, later Firmenbuch and GISA) is one adapter behind a common interface, so a source is added or changed without touching the others (REQ-MAINT-003). Adding one touches only its own module, the registry, its tests and its integration note:

1. Write `checks/sources/<source>.py` with a subclass of `SourceAdapter` (`checks/sources/base.py`):
   - `source`: the name reported in every result, e.g. `"BMF"`; unique.
   - `checks`: the check names it answers, e.g. `("onBmfList",)`; each check belongs to one adapter only.
   - `applies_to(partner)` (optional): return `False` when the source doesn't apply, e.g. non-Austrian partners; its checks are then `NOT_APPLICABLE` (REQ-FUNC-038).
   - `run(partner, deadline)`: return one result per check, built with `self.result(...)` or `self.unknown(...)`. Give up by `deadline` (8 s incl. one retry, REQ-INT-013) and `return self.unavailable("TIMEOUT")` or another short error code instead of raising. For a web service, call it with `post_within_budget(url, deadline, ...)` from `checks/sources/http.py`: it retries a timeout, network error or HTTP 5xx once within the budget (REQ-REL-003) and raises `SourceUnavailable(code)` otherwise.
2. Add one instance to `ADAPTERS` in `checks/sources/__init__.py`. The list order is the order of the checks in the response.
3. Add `tests/test_checks_<source>.py` with the source mocked, and `docs/sources/<source>.md` (REQ-INT-016).

The runner (`checks/runner.py`) only knows this interface: it calls all applicable adapters in parallel, and if one raises, overruns its budget or returns checks it didn't declare, only that adapter's checks become `UNKNOWN` / `SOURCE_UNAVAILABLE` (REQ-FUNC-039). The registry is checked when the app starts (`checks/sources/registry.py`), so a duplicate source or check name fails in CI. Adapters don't import Django, so they can be tried out in a plain Python shell:

```python
import time
from checks.results import Partner
from checks.sources.vies import ViesAdapter

ViesAdapter().run(Partner("ATU12345678", "Muster Bau GmbH"), time.monotonic() + 8)
```

## Tech stack

Python + Django (templates, admin, translations, ORM), Keycloak for user login (OpenID Connect via `mozilla-django-oidc`), PostgreSQL, `requests` + `feedparser` for the data sources, pytest + ruff, GitHub Actions for CI, deployment and the daily sync trigger. Hosting: Render (app, Frankfurt), Neon (PostgreSQL, EU), Brevo (SMTP email).

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
- [ ] Every new test names the SRS requirement ID(s) it verifies in its docstring (see [Test names and SRS requirement IDs](#test-names-and-srs-requirement-ids))
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
