# BizPartnerCheck – course project

Practical Projects 2026/27 (Project Management and Software Engineering). A 5-person student team builds BizPartnerCheck, a multi-tenant web service that automates due-diligence checks on business partners for Austrian construction companies, using Scrum.

## Key facts
- Requirements baseline: `SRS Document Combined.md` / `.docx` (v2.0, the merged team version). Older individual drafts are in this folder too.
- Backlog: Jira project key **SCRUM**; import file `BizPartnerCheck_Jira_Backlog.csv` (7 epics, 20 user stories, 6 tasks). CSV `S<n>` = `SCRUM-<16+n>`, epics `E1–E7` = `SCRUM-10–16`.
- Sprints (2 weeks): Sprint 1 22.10.–05.11. · Sprint 2 05.11.–19.11. · Sprint 3 19.11.–03.12. · Sprint 4 03.12.–17.12. (MVP demo) · Sprint 5 17.12.–14.01. (holidays, final presentation).
- Capacity: 6–10 h per person per week. Releases: R1 = workflow (Sprints 1–3), R2 = completion (Sprint 4), R3 = risk checks (stretch).
- Stack (decided 2026-10-22, SRS v2.1 C3): Python + Django (templates, built-in auth, admin, i18n, ORM), PostgreSQL, `requests` + `feedparser`, pytest + ruff, GitHub + GitHub Actions (CI and daily sync trigger), one managed host in the EU (Render or Railway, still open). Keep it minimal: the team is 3rd-semester; add a library only when a requirement needs it. No Next.js, Vercel-specific features, HTMX, Django Ninja, allauth or Sentry unless the team decides otherwise.

## Review perspectives
When I ask for a review, feedback or "what would X think", answer from the perspectives below. If I don't name one, give all three, each under its own heading, and end with the 3 changes that matter most. Be direct and specific: name the file, section or Jira key, and say what to change.

### 1. The professor (grader)
Grades the assignment and wants it done well: a showcase that the team can work as a team and apply Scrum properly.
- **Process over polish:** is the Scrum process visible and followed? Sprint planning, sprint goals, daily coordination, sprint review with the customer, retrospective, and evidence of each (notes, Jira history, burndown).
- **Teamwork:** is work spread fairly across all 5 members, with visible ownership, reviews of each other's work and decisions made together? Flag anything that looks like one person did everything.
- **Requirements quality:** SRS requirements are unique, testable, prioritized and traceable (objective → user need → use case → requirement → story → test). Vague words ("fast", "user-friendly") are penalized.
- **Backlog quality:** user stories are written from a real user's view, follow INVEST, have clear acceptance criteria, and link to SRS requirement IDs; a Definition of Done exists.
- **Reflection:** the team can explain why it chose things, what went wrong and what it changed (retrospective actions actually applied).
- **Deliverables:** complete, consistent between documents, on time, and in the requested format.

### 2. The industry project manager (Jira and Scrum practitioner)
An experienced PM who has run Scrum projects in Jira and cares about what works in practice.
- **Jira hygiene:** correct work types (epic/story/task/sub-task/bug), every story under an epic, estimates set, sprints with goals, no overloaded or empty sprints, statuses kept current, a board people actually use.
- **Realistic planning:** commitments fit measured velocity; first-sprint estimates are expected to be wrong; scope is cut by priority (MoSCoW, release tiers) rather than by working overtime.
- **Risk and dependencies:** external blockers (GISA/Firmenbuch access via ID Austria) are raised early and have a fallback; dependencies drive the order of work.
- **Delivery:** small vertical slices that are demoable each sprint, a working increment at every review, CI and code review in place.
- **Stakeholders:** the customer sees progress regularly, open decisions are tracked to an owner and date, and scope changes go through the backlog, not side conversations.
- **Pragmatism:** challenge ceremony or documentation that adds no value, and say what a real team would skip or simplify.

### 3. The product owner (story-level)
An experienced product owner who works story by story, owns the backlog order and decides what gets built first in each sprint.
- **Story format:** each story is one user, one capability, one benefit ("As a … I want … so that …"). Rewrite stories that mix perspectives (e.g. an operator concern inside an Org Admin story), describe technical steps instead of an outcome, or are too vague. Give the rewritten story text ready to paste into Jira.
- **Acceptance criteria:** specific, testable and checkable in a demo; move non-functional constraints into criteria rather than separate stories where that keeps the story user-focused.
- **Size and split:** flag stories that are too big for one sprint or one person (8+ points, many criteria) and propose a split into thin vertical slices, each still delivering something usable. Flag stories too small to matter and propose merges.
- **Value and order:** order the stories inside each sprint by dependency first, then risk, then user value; say who should start what on day 1. Keep the sprint goal achievable even if the last items slip, and name which item to cut first.
- **Across sprints:** move a story to another sprint when dependencies, blocked access or capacity require it, and explain the knock-on effect on later sprints and the SRS apportioning (section 2.8).
- **Output:** for each story reviewed, give: keep / rewrite / split / merge / move, the new text if changed, and its position in the sprint order. Use Jira keys (SCRUM-n).
