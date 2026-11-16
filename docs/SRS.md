# Software Requirements Specification
## For BizPartnerCheck

Version 2.4 (combined team version)  
Prepared by Luka Herceg, Elias Hoffstadt, WŚ and Tony  
Practical Projects 2026/27  
2026-10-22

## Table of Contents
<!-- TOC -->
<!-- TOC -->

## Revision History

| Name | Date | Reason For Changes | Version |
|------|------|--------------------|---------|
| Luka Herceg | 2026-10-21 | Individual draft (template structure, sprint plan) | 0.1 |
| Elias Hoffstadt | 2026-10-21 | Individual draft (business objectives, use cases, traceability) | 1.0 |
| WŚ | 2026-10-21 | Individual draft (RE process, reconciliation of customer statements, HFU semantics) | 0.1 |
| Tony | 2026-10 | Individual draft (result semantics, open decisions, sign-off) | 0.1 |
| Team | 2026-10-22 | Combined version: best parts of the four drafts merged, conflicts resolved (Appendix C) | 2.0 |
| Team | 2026-10-22 | Tech stack decided: Python/Django with built-in auth, PostgreSQL, one managed host (C3, C10, A5, FUNC-003, FUNC-024, SEC-002, SEC-004, PORT-001, OD-08 updated) | 2.1 |
| Team | 2026-11-04 | HFU check aligned with the HFU web service documentation (spike SCRUM-19): live SOAP query by VAT number only, no name or FN fallback (3.1.3, FUNC-034, FUNC-071, A4, Appendix D Q4, OD-01, OD-05); OD-06 updated with the ID Austria holder and the GISA application | 2.2 |
| Team | 2026-11-04 | Hosting decided (OD-08 closed): app on Render, database on Neon, email via Brevo SMTP, all in EU regions (C3, A5, 3.1.3, 3.5) | 2.3 |
| Luka Herceg | 2026-11-04 | Brevo sender is temporarily Luka Herceg's private email address; it must be changed to a team email address (later: an address on the team's own domain) before the app is used beyond testing (OD-08) | 2.4 |
| Luka Herceg | 2026-11-04 | SRS added to the code repository as `docs/SRS.md`, which is now the master copy for the team and coding agents (review of PR #9) | 2.4 |

## 1. Introduction
BizPartnerCheck is a multi-tenant web service that runs the due-diligence checks a construction company must perform on a prospective business partner in one request, and stores the result as evidence. Section 1 states purpose, scope and process; Section 2 describes the business case, stakeholders, use cases and constraints; Section 3 lists the verifiable requirements; Section 4 explains how they are verified; Section 5 holds supporting material.

### 1.1 Document Purpose
This SRS defines **what** BizPartnerCheck shall do, not how it is built. Once accepted by the customer it is the baseline for design, implementation, testing and acceptance; until signed off (Appendix G) it is a draft, and requirements that depend on open decisions (Appendix F) are provisional.

| Audience | How they use this document |
|---|---|
| Customer (course lecturer acting as client) | Confirms scope, priorities and acceptance criteria |
| Development team (5 students) | Plans sprints and derives design and tasks from requirement IDs |
| Testers / reviewers | Derive test cases from Section 3 and track them in Section 4 |
| Operator (Super Admin) | Understands operating, security and compliance obligations |

### 1.2 Product Scope
**BizPartnerCheck, release 1.0.** A user, or the customer's own software through the API, enters a partner's VAT number and name; BizPartnerCheck runs all checks against the official sources within seconds, returns a detailed result per check, and stores a timestamped record proving the check was done.

| In scope (release 1.0) | Out of scope |
|---|---|
| VAT check for all EU VAT numbers; fake-company, HFU, company-register, business-license and required-license checks for Austrian partners; company-name check | Legal advice or a binding "contract / don't contract" decision |
| REST API with revocable tokens; JSON and HTML responses | Storing documents (certificates, register extracts, PDFs) |
| Organization self-registration, four roles, multi-tenancy | Automatic or scheduled re-checks of partners |
| Request log, review web app, housekeeping, audit log | PDF export (a browser print of the HTML page is possible) |
| Daily synchronization of list-based sources | Self-hosted / on-premise installation; mobile apps; billing |
| Optional (R3): person-based and financial risk findings | Numeric risk scores; national registers outside Austria |

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| API token | Long-lived secret with which a client system authenticates against the API on behalf of one user; revocable at any time |
| BMF | Bundesministerium für Finanzen – Austrian Ministry of Finance |
| Check / check request | One verification against one source / one call that runs all applicable checks for one partner and is stored as evidence |
| Fake-company list | BMF list of sham companies (Scheinunternehmen), published as an RSS feed |
| FN | Firmenbuchnummer – Austrian company register number (up to 6 digits plus a check letter, e.g. 123456a) |
| Firmenbuch | Austrian company register; partially open data under the EU High Value Datasets (HVD) directive |
| GISA | Gewerbeinformationssystem Austria – Austrian business license register |
| HFU list | Social-insurance list of companies that can be contracted without contractor liability (Haftungsfreistellung). Most companies are not listed; for an unlisted partner the contractor must withhold part of the payment |
| ID Austria | Austrian electronic identity, needed to register for some government interfaces |
| Organization / tenant | A customer company registered in BizPartnerCheck; its data is isolated from all other tenants |
| UID / VAT number | Value-added-tax identification number (Austria: "ATU" + 8 digits) |
| VIES | VAT Information Exchange System of the European Commission |

### 1.4 References

| # | Title (owner) | Location | Type |
|---|---|---|---|
| R1 | Practical Projects 2026/27 – project brief, 01a_PracticalProject.pptx (course lecturer) | Course folder | Normative |
| R2 | Customer meeting notes 2026-10-08, project manage.docx; question list projectmanag.pdf (team) | Team folder | Normative |
| R3 | Lecture slides on Requirements Engineering (course lecturer) | Course folder | Informative |
| R4 | SRS template (jam01) | [github.com/jam01/SRS-Template](https://github.com/jam01/SRS-Template) | Informative |
| R5 | VIES technical information (European Commission) | [ec.europa.eu/taxation_customs/vies](https://ec.europa.eu/taxation_customs/vies/#/technical-information) | Interface |
| R6 | List of sham companies, RSS (BMF) | [service.bmf.gv.at/service/allg/lsu](https://service.bmf.gv.at/service/allg/lsu/) | Interface |
| R7 | HFU list web service (ÖGK) | [oegk.at – HFU list](https://www.oegk.at/cdscontent/load?contentid=10008.731907) | Interface |
| R8 | Firmenbuch open data IWG/HVD (Ministry of Justice) | [justizonline.gv.at/jop/web/iwg](https://justizonline.gv.at/jop/web/iwg) | Interface |
| R9 | GISA interface (BMWET) | [bmwet.gv.at – GISA-Schnittstelle](https://www.bmwet.gv.at/Themen/Unternehmen/GISA_Gewerbeinformationssystem/GISA_Schnittstelle.html) | Interface |
| R10 | General Data Protection Regulation (EU) 2016/679 | [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | Normative |
| R11 | OWASP Top 10; WCAG 2.1 (OWASP; W3C) | [owasp.org/Top10](https://owasp.org/Top10/); [w3.org/TR/WCAG21](https://www.w3.org/TR/WCAG21/) | Informative |

### 1.5 Document Overview
The keywords **shall** (mandatory), **should** (recommended) and **may** (optional) express obligation. Each requirement has a unique, immutable ID `REQ-[AREA]-[NNN]` and is listed with its statement, acceptance criteria, priority **P** (MoSCoW: M Must, S Should, C Could, W Won't), verification method **V** (T Test, D Demonstration, I Inspection, A Analysis) and **Trace** (use case UC, user need UN, business objective BO or constraint C). Releases: R1 workflow, R2 completion, R3 extensions (2.8). Times are UTC, ISO 8601. Changes are recorded in the Revision History; IDs are never reused.

### 1.6 Requirements Engineering Process
The customer stated that the process matters more than polish. The team (1) analysed the brief – problem, vision, five data sources (→ 2.1, 3.1.3); (2) prepared twelve questions for the requirements meeting (→ Appendix D); (3) elicited answers and further requirements in the meeting of 2026-10-08; (4) wrote four independent SRS drafts; (5) merged them, reconciling contradictory customer statements and draft decisions (→ Appendix C); (6) traced objectives to needs, use cases, requirements and verification (→ Appendix E); and (7) validates open decisions with the customer before sign-off (→ Appendices F, G). Later changes follow REQ-CM-001.

## 2. Product Overview

### 2.1 Business Case and Objectives
Construction companies in Austria must check every subcontractor before contracting it. Under the contractor liability rules (Auftraggeberhaftung), a client can be held liable for unpaid social-insurance contributions and wage taxes of a subcontractor unless the subcontractor is on the HFU list – otherwise part of the payment must be withheld. Contracting a company identified by the Ministry of Finance as a sham company adds further legal and financial risk. Today the checks are done by hand on five separate portals (VIES, BMF, ÖGK, Firmenbuch, GISA), and the proof is usually a screenshot or printout: slow, error-prone and hard to prove in an audit.

**Vision:** "Fully integrate and automate business partner due diligence check for construction companies." (R1)

| ID | Business objective | Success metric | P |
|---|---|---|---|
| BO-1 | Automate all legally relevant partner checks, plus a company-name check, in a single request | One API call returns all check results within 10 s (p95) | M |
| BO-2 | Provide audit-proof evidence for every check | 100 % of check requests stored with timestamp, requester, input and per-check results | M |
| BO-3 | Let customers integrate checks into their own software (machine-to-machine is the primary channel) | All check functions available through the token-secured REST API; no manual step | M |
| BO-4 | Serve many customer companies on one low-cost platform | One multi-tenant deployment within free/low tiers; scales to the targets of REQ-PERF-005 | M |
| BO-5 | Keep liability with the using company | Every response and the terms of use state that BizPartnerCheck carries no liability | M |
| BO-6 | Deliver a working end-to-end workflow within the course (~3 months, 6–10 h/week per person); workflow before polish | All Must requirements of R1 accepted by the final presentation (REQ-DEAD-001) | M |
| BO-7 | Stay extensible to further countries and risk checks | A new source is added as one adapter without changing the others (REQ-MAINT-003) | C |

**Project success (customer definition):** a working, well-documented workflow – an organization registers, its admin creates users and tokens, a Request User runs a check through UI or API, and a Review User inspects the stored record; every source returns a defined result, never a silent failure; requirements, decisions and tests are traceable.

### 2.2 Product Perspective
BizPartnerCheck is a new, standalone product; it replaces no existing system. It sits between the customer's software (ERP, procurement or subcontractor management) and five public data sources. Client systems call the REST API, staff use the web app, and BizPartnerCheck queries live sources or its own copy of list-based sources, combines the answers and stores the request as evidence.

```
 Customer ERP  ──REST/JSON──▶ ┌────────────────────────────┐ ──▶ VIES (EU VAT, live)
 Customer staff ──Browser───▶ │       BizPartnerCheck      │ ──▶ Firmenbuch (live, credential)
                              │ Web app · API · Check      │ ──▶ GISA (live, credential)
 GitHub Actions (daily) ─────▶ │ engine · Sync job · DB     │ ◀── BMF fake-company RSS (daily sync)
 Email service ◀───────────── └────────────────────────────┘ ◀── ÖGK HFU list (live query)
```

The project team develops the service and operates it on public managed cloud infrastructure. As a course project no formal SLA is offered; the targets in 3.3 are the agreed service levels.

### 2.3 Product Functions
- **Onboarding, users, tokens:** free organization registration with email verification; the Org Admin manages users, roles and API tokens.
- **Partner check:** one request runs the VAT, name, fake-company, HFU, company-register, business-license and required-license checks, returned as JSON or HTML.
- **Evidence, review, housekeeping:** every request is stored with timestamps and requester, reviewed as one report, deletable by the Org Admin; actions and API calls are audited.
- **Operations:** daily, logged sync of list sources; Super Admin manages organizations; optional (R3) person-based and financial risk findings.

### 2.4 Product Constraints

| ID | Constraint | Kind |
|---|---|---|
| C1 | The system must run as a web service on publicly available managed infrastructure; the customer operates no server. | External, mandatory |
| C2 | The system must use a relational database. | External, mandatory |
| C3 | The system is built with Python and Django (templates, built-in authentication, admin, translations), PostgreSQL, the app hosted on Render, the database on Neon and email sent through Brevo's SMTP service, all in EU regions, with as few extra libraries as possible: Python/Django chosen for the team's existing Python skills (decision 2026-10-22), hosting decided on 2026-11-04 (see 3.5). | Internal, mandatory |
| C4 | The system must be multi-tenant: one deployment on one domain serves all organizations. | External, mandatory |
| C5 | The system must offer a RESTful API with token-based authentication; tokens must be listable and revocable in the web app. | External, mandatory |
| C6 | The UI must be available in English and German. | External, mandatory |
| C7 | The system must store requests and results, never documents. | External, mandatory |
| C8 | Firmenbuch and GISA require registration (ID Austria) by the operator; VIES, BMF and ÖGK are free. | External, mandatory |
| C9 | Personal data must be processed in line with the GDPR (R10). | External, mandatory |
| C10 | Authentication must use Django's built-in authentication system (password hashing, sessions, password reset), not self-built credential handling. | Internal, mandatory |
| C11 | Capacity is limited to ~3 months with 6–10 h per developer per week. | Internal, mandatory |

### 2.5 User Characteristics

**Stakeholders**

| ID | Stakeholder | Interest |
|---|---|---|
| SH-1 | Customer (course lecturer acting as client) | Defines needs and priorities, accepts the delivery |
| SH-2 | Customer organizations (construction companies) | Fast, provable due diligence; remain responsible for contracting decisions |
| SH-3 | Organization Admin | Sets up users and tokens, does housekeeping |
| SH-4 | Request User (person or client system) | Starts checks and uses the results |
| SH-5 | Review User (compliance, purchasing) | Proves that checks were done |
| SH-6 | Super Admin (operator, project team) | Runs the platform, manages tenants, keeps it available and cheap |
| SH-7 | Development team (5 students) | Builds, tests and delivers within the course |
| SH-8 | Data providers (European Commission, BMF, ÖGK, Ministry of Justice, BMWET) | Fair use within their terms and rate limits |
| SH-9 | Auditors and authorities (indirect) | Rely on the documented evidence |
| SH-10 | Partner companies and their managers (indirect) | Data subjects; lawful and minimal processing of their data |

**User classes**

| Role | Characteristics | Frequency | Access |
|---|---|---|---|
| Super Admin | Project team member, technically skilled | Rare | All organizations, administrative functions only – never request content |
| Organization Admin | IT or compliance lead, moderately technical | Setup, then occasional | Own organization: users, tokens, requests, audit log, deletion |
| Request User | Often a technical system (ERP) acting for the organization; may be a buyer using the web form | Frequent, often automated | Start checks; view status and results of own requests |
| Review User | Compliance or purchasing staff, not technical | Weekly or during audits | Read all check requests of own organization |

Roles are additive: one user may hold several roles, and the first user of a new organization holds all three organization roles. Users work in German or English; the language follows the browser.

**User needs**

| ID | Need | Stakeholder | BO |
|---|---|---|---|
| UN-01 | Prove for every partner when it was checked, by whom and with which result | SH-5, SH-9 | BO-2 |
| UN-02 | Check a partner in one step instead of five portals | SH-4 | BO-1 |
| UN-03 | Trigger checks from our own software without a human logging in | SH-2, SH-4 | BO-3 |
| UN-04 | Control who may start checks and read the log; cut off a leaked token at once | SH-3 | BO-3 |
| UN-05 | Get a clear result per check, including when a source could not answer | SH-4, SH-5 | BO-1, BO-5 |
| UN-06 | Check partners from other EU countries, at least their VAT number | SH-2 | BO-1 |
| UN-07 | Use the web app in German or English | SH-3–SH-5 | BO-4 |
| UN-08 | Delete old requests completely | SH-3 | BO-2 |
| UN-09 | Keep our data invisible to all other customers | SH-2 | BO-4 |
| UN-10 | Know how current the list data was at the time of a check | SH-5, SH-9 | BO-2 |
| UN-11 | Register for free and start without installing anything | SH-2 | BO-4 |
| UN-12 | Manage tenants and keep the service stable under load at low cost | SH-6 | BO-4 |
| UN-13 | Have personal data processed lawfully and minimally | SH-10 | BO-4 |
| UN-14 | Detect hidden risk through persons linked to fake companies and through finances | SH-2 | BO-7 |

### 2.6 Use Cases

| ID | Use case | Primary actor | Needs | Release |
|---|---|---|---|---|
| UC-01 | Register organization | Visitor (becomes Org Admin) | UN-11 | R1 |
| UC-02 | Manage users and roles | Org Admin | UN-04, UN-09 | R1 |
| UC-03 | Manage API tokens | Org Admin, any user (own) | UN-03, UN-04 | R1 |
| UC-04 | Run partner check via API | Request User (client system) | UN-02, UN-03, UN-05, UN-06 | R1 |
| UC-05 | Run partner check via web form | Request User (person) | UN-02, UN-05, UN-07 | R1 |
| UC-06 | Review check evidence (list as one report, detail) | Review User | UN-01, UN-10 | R1 |
| UC-07 | Delete check requests | Org Admin | UN-08 | R2 |
| UC-08 | View audit log | Org Admin | UN-01, UN-04 | R2 |
| UC-09 | Synchronize list sources | System (scheduler) | UN-10 | R1 |
| UC-10 | Administer platform (incl. bootstrap of first Super Admin) | Super Admin | UN-12 | R1 |
| UC-11 | Assess additional risks | Request / Review User | UN-14 | R3 |

**UC-04 Run partner check via API (core use case)**

| Field | Description |
|---|---|
| Precondition | Organization is active; the caller holds a valid, non-revoked token of a user with the Request User role. |
| Trigger | Client system needs to contract or re-check a partner. |
| Main flow | 1. Client sends `POST /api/v1/checks` with vatNumber, companyName and optional FN, address, required license codes and reference. 2. System authenticates the token and checks the rate limit. 3. System validates and normalizes the input. 4. System runs all applicable checks in parallel, each with a time budget. 5. System stores the complete request atomically. 6. System returns one result per check as JSON or HTML. |
| Alternative flows | 2a. Token missing, invalid or revoked → 401. 2b. Rate limit exceeded → 429, nothing stored. 3a. Input invalid → 400 with field errors, nothing stored. 4a. A source fails or times out → that check is UNKNOWN / SOURCE_UNAVAILABLE, the others continue. 4b. Partner not Austrian → Austria-only checks are NOT_APPLICABLE. 4c. Several or name-only matches → UNKNOWN / AMBIGUOUS_MATCH. |
| Postcondition | The request is stored immutably and visible to the organization's Review Users; an audit entry exists. |
| Requirements | REQ-FUNC-030…049, REQ-SEC-003 |

### 2.7 Assumptions and Dependencies

| ID | Assumption / dependency | Impact if false |
|---|---|---|
| A1 | The team obtains access to GISA and Firmenbuch (account, ID Austria, keys) by Sprint 3 (REQ-POC-003). | Those checks return UNKNOWN / SOURCE_UNAVAILABLE and are demonstrated against test doubles. |
| A2 | VIES, the BMF RSS feed and the ÖGK HFU service stay free and reachable. | The affected check is degraded; the last synced copy is used where possible. |
| A3 | About 80 % of checked partners are Austrian (R2). | More NOT_APPLICABLE results; value per check drops. |
| A4 | Fake-company entries contain VAT number or FN, so matching need not rely on names (the HFU service is queried by VAT number only, see FUNC-034). | Name-only matching gives false hits; more AMBIGUOUS_MATCH results. |
| A5 | The free tiers of Render, Neon and Brevo cover course-level load; Neon's free database doesn't expire. Render's free web service sleeps when idle, so the team wakes it before demos. | A paid tier or another provider is needed (REQ-COST-001). |
| A6 | The customer is available for feedback at least once per sprint. | Acceptance is delayed; priorities may be wrong. |

### 2.8 Apportioning of Requirements
Release R1 is the minimum end-to-end workflow; R2 completes the product; R3 holds extensions. **Fallback rule from the customer:** if time runs out, the workflow comes first – the roles may be reduced to Org Admin and User (Request + Review merged) while R1 stays intact.

| Sprint (course roadmap) | Dates | Release | Requirements |
|---|---|---|---|
| Spec phase | 08.10.–22.10. | – | This SRS; POCs REQ-POC-001…003 started |
| Sprint 1 | 22.10.–05.11. | R1 | Platform and CI, registration, login, roles, tenant isolation, VAT and name check end-to-end (FUNC-001…003, 010…013, 030…032, 045; BUILD-*, INST-*) |
| Sprint 2 | 05.11.–19.11. | R1 | Tokens, rate limit, list syncs, fake-company and HFU checks, evidence log (FUNC-020…023, 033, 034, 039…041, 050, 051, 070…073; SEC-001…005) |
| Sprint 3 | 19.11.–03.12. | R1 | Firmenbuch and GISA checks, review web app, HTML response, web form (FUNC-035…038, 042, 046…048, 052…055; INT-010…016) |
| Sprint 4 | 03.12.–17.12. | R2 | Housekeeping, audit log, Super Admin console, German UI, hardening, QoS tests – **MVP demo** (FUNC-004, 005, 014, 024, 060…063, 074; INT-001…005; remaining QoS) |
| Sprint 5* | 17.12.–14.01. | R3 | Risk checks if capacity allows (FUNC-080…082); polish, documentation, final presentation |

## 3. Requirements
All requirements use the template fields in compact form: ID, statement, acceptance criteria, priority (P), verification (V) and trace. The rationale of each group is given above its table.

### 3.1 External Interfaces

#### 3.1.1 User Interfaces
Screens: landing page (Register, Login), registration, login and password reset, check form, check result, request list with filters, request detail, user management, token management, audit log, Super Admin console (organizations, sync log, source health).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-INT-001 | The UI shall be available in German and English and pick the language from the browser's `Accept-Language` header, defaulting to English. | Browser set to `de-AT` shows German; `fr-FR` shows English; no hard-coded UI strings. | M | T | C6, UN-07 |
| REQ-INT-002 | Users should be able to switch the language manually; the choice persists across sessions. | Choice survives logout and login. | S | D | UN-07 |
| REQ-INT-003 | The UI shall work in current Chrome, Firefox, Edge and Safari at widths from 360 px to 1920 px. | All screens usable at 360 and 1440 px in each browser. | M | I | UN-11 |
| REQ-INT-004 | The UI should meet WCAG 2.1 AA for keyboard use, labels and contrast; check states are shown as text and colour, never colour alone. | Automated accessibility scan shows no critical violations. | S | T | R11 |
| REQ-INT-005 | Every list shall show an empty state; every failed action shall show a message naming the problem and the fix, without technical details. | Each screen inspected with no data and with a forced server error. | M | I | UN-05 |

#### 3.1.2 Hardware Interfaces
None. Users need only a device with a current browser; no customer hardware or local server is required.

#### 3.1.3 Software Interfaces
**Provided interface – BizPartnerCheck REST API v1**

| Method and path | Purpose | Authorization |
|---|---|---|
| `POST /api/v1/checks` | Run a partner check; returns the stored result | Request User |
| `GET /api/v1/checks/{id}` | One stored request with full detail | Review User, Org Admin; Request User (own) |
| `GET /api/v1/checks?from=&to=&vatNumber=&page=` | List requests – the "one report" | Review User, Org Admin; Request User (own) |
| `DELETE /api/v1/checks/{id}` | Delete a request completely | Org Admin |
| `GET/POST /api/v1/tokens`, `DELETE /api/v1/tokens/{id}` | List, create, revoke tokens | Org Admin (all of org); any user (own) |
| `GET /api/v1/health` | Status of database and each source | Public |

**Required interfaces – data sources**

| Source | Data used | Access | Matching key | Freshness |
|---|---|---|---|---|
| VIES (R5) | VAT validity, registered name and address | Live call; free | VAT number | Live |
| BMF fake-company list (R6) | Name, FN, VAT number, address, date listed | RSS feed imported into own DB; free | VAT, then FN, then normalized name | Daily sync |
| ÖGK HFU list (R7) | Companies on the HFU list | SOAP web service (v3.0), live query per check; each query carries the requesting organization's UID; a daily import only if a full-list export is confirmed (SCRUM-19); free | VAT number (UID) only; no lookup by name or FN | Live |
| Firmenbuch (R8) | Registration status, FN, legal form, managers; latest financial statement (R3) | Live call; operator credential (ID Austria) | FN, else name and VAT | Live |
| GISA (R9) | Business licenses and responsible persons | Live call; operator credential (ID Austria) | VAT or FN, else name | Live |
| Brevo (SMTP) | Verification, invitation and password-reset emails | SMTP with TLS; sender address on a verified domain for reliable delivery | – | – |

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-INT-010 | The API shall be versioned in the path (`/api/v1`); breaking changes only under a new version. | Routes and changelog inspected. | M | I | C5 |
| REQ-INT-011 | Every endpoint except health shall require a valid Bearer token or web session. | Call without or with unknown token returns 401. | M | T | C5, UC-04 |
| REQ-INT-012 | The API shall use standard status codes (200, 201, 400, 401, 403, 404, 429, 500) with a JSON error body containing a stable error code and message. A check with unavailable sources still returns 200. | Negative test for every code; source outage returns 200 with UNKNOWN. | M | T | UC-04 |
| REQ-INT-013 | Each external source shall have a time budget of at most 8 s per check request, including any retry. | A stub that never answers yields UNKNOWN / SOURCE_UNAVAILABLE after ≤ 8 s. | M | T | UN-05 |
| REQ-INT-014 | Credentials for external sources shall be kept only in the platform's secret configuration, never in code, database or browser. | Repository and database scan find no credentials. | M | I | C8 |
| REQ-INT-015 | The API should be described in an API reference (OpenAPI 3 file or a written reference) published with the service. | Reference covers every implemented route, its input and its response. | S | I | UN-03 |
| REQ-INT-016 | Each source integration shall be documented: source owner, fields used, access method, error cases, terms of use. | One integration note per source in the repository. | M | I | REQ-POC-001 |

### 3.2 Functional

#### 3.2.1 Organization Registration and Login
*Rationale:* organizations must be able to start for free without installation (R2, UN-11); authentication uses Django's built-in system (C10).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-001 | The landing page shall offer Register and Login; a visitor shall be able to register an organization for free with organization name, address, VAT number, first name, last name, email and password, accepting the terms of use. | Missing fields and malformed VAT numbers rejected; on success the organization and its first user (all three org roles) exist as "unverified". | M | T | UC-01, UN-11 |
| REQ-FUNC-002 | The system shall send a verification link and activate the organization only after it is opened; the link expires after 24 h and can be re-sent. | Unverified admin cannot log in; verified can; expired link offers resend. | M | T | UC-01 |
| REQ-FUNC-003 | Users shall log in with email and password using Django's built-in authentication, with logout and password reset by email. | Login with correct and wrong credentials; reset flow end-to-end. | M | T | C10, UC-01 |
| REQ-FUNC-004 | The system should check the registering organization's own VAT number via VIES. | Invalid → registration rejected; VIES unavailable → accepted and marked "VAT unverified". | S | T | UC-01 |
| REQ-FUNC-005 | A setup script shall create exactly one initial Super Admin with a one-time password that must be changed at first login. Self-registration of individual users without an Org Admin is not part of release 1.0 (W). | Script run on an empty system; forced password change observed. | M | T | UC-10 |

#### 3.2.2 Users, Roles and Tenants
*Rationale:* the customer wants separate roles for starting checks and reading the log (R2); the service is multi-tenant (C4).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-010 | An Org Admin shall be able to create, edit, deactivate and delete users of the own organization and assign the roles Org Admin, Request User and Review User (additive). New users receive an invitation email; unused invitations expire after 7 days. | Created user logs in with exactly the assigned rights; deactivated user cannot log in. | M | T | UC-02, UN-04 |
| REQ-FUNC-011 | The system shall prevent removing or deactivating the last Org Admin and the last Review User of an organization (except when the whole organization is deleted). | Attempt rejected with a message; user remains. | M | T | UC-02 |
| REQ-FUNC-012 | The system shall enforce the permissions of Appendix A on every web and API action on the server side. | Every forbidden role/action pair returns 403. | M | T | UN-04 |
| REQ-FUNC-013 | A user shall only ever see data of the own organization; every query is scoped by organization. | Automated test: user of org A requesting any resource of org B receives 404. | M | T | C4, UN-09 |
| REQ-FUNC-014 | The Super Admin shall be able to create, list (name, registration date, number of checks), deactivate, reactivate and – on request – delete organizations including all their data. | Users and tokens of a deactivated org are rejected; after deletion no record of it remains. | M | T | UC-10, UN-12 |

#### 3.2.3 API Token Management
*Rationale:* client systems authenticate with tokens; a leaked or shared token must be removable at once (R2, C5). Tokens are valid indefinitely unless revoked, as the customer requested.

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-020 | An Org Admin shall be able to create named tokens for any user of the organization, and users should be able to create tokens for themselves. Tokens never expire by default; an expiry date is optional. | Token works for API calls; token past its expiry returns 401. | M | T | UC-03, UN-03 |
| REQ-FUNC-021 | A token shall grant exactly the permissions of its owner's roles at the time of use, never more. | Review-only user's token cannot start a check (403). | M | T | UN-04 |
| REQ-FUNC-022 | The full token value shall be shown once at creation; afterwards only name, first 8 characters, owner, creation and last-use date. | No screen or response shows a full token after creation. | M | T | UC-03 |
| REQ-FUNC-023 | The owner and the Org Admin shall be able to list and revoke tokens; a revoked token is rejected within 60 s. Deactivating or deleting a user revokes all their tokens. | Call with revoked token or token of deactivated user returns 401. | M | T | UC-03, UN-04 |
| REQ-FUNC-024 | OAuth 2.0 client-credentials token issuing is not part of release 1.0; tokens are the app's own hashed API keys (FUNC-020…023). | – | W | – | C5, C10 |

#### 3.2.4 Partner Check
*Rationale:* the core value of the product (R1, BO-1). The customer decides whether to contract, so the system returns a detailed result per check, not a verdict or score (R2).

**Result values.** Each check answers one yes/no question (the customer asked for a Boolean per check) and returns one of four values plus a data timestamp (time of query for live sources, time of last successful sync for list sources):

| Value | Meaning |
|---|---|
| TRUE / FALSE | The source answered; the answer to the check question is yes / no |
| UNKNOWN | No reliable answer; reason SOURCE_UNAVAILABLE, AMBIGUOUS_MATCH or NO_DETAILS_FOUND – never shown as a pass or fail |
| NOT_APPLICABLE | The check does not apply (e.g. Austrian register for a German partner) |

Because TRUE is not always the good outcome, each check states its **expected value**:

| Check (question) | Source | Expected value |
|---|---|---|
| `vatValid` – Is the VAT number valid? | VIES | TRUE |
| `nameMatchesVat` – Does the given name match the VAT registration? | VIES | TRUE |
| `listedAsFakeCompany` – Is the partner on the fake-company list? | BMF | FALSE |
| `onHfuList` – Is the partner on the HFU list? | ÖGK | informational: FALSE is normal and means part of the payment must be withheld |
| `inCompanyRegister` – Is the partner actively registered? | Firmenbuch | TRUE |
| `inBusinessLicenseRegister` – Does the partner hold at least one active license? | GISA | TRUE |
| `hasRequiredLicenses` – Are all requested license codes active? | GISA | TRUE (NOT_APPLICABLE if none requested) |

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-030 | The system shall accept a check with vatNumber and companyName (required), FN, address, required license codes and an internal reference (optional); input is normalized (country prefix, spaces, case) and invalid input rejected with field errors before any source is called. | Missing VAT or name returns 400; nothing stored. | M | T | UC-04, UC-05 |
| REQ-FUNC-031 | **vatValid:** the system shall check the format and query VIES for any EU member state. | Valid AT and DE numbers → TRUE; invalid → FALSE; VIES down → UNKNOWN. | M | T | UN-06 |
| REQ-FUNC-032 | **nameMatchesVat:** the system shall compare the given name with the VIES-registered name, ignoring case, punctuation and legal-form suffixes, and report the registered name. | "Muster Bau GmbH" vs "MUSTER BAU GMBH" → TRUE; other company → FALSE. | M | T | R2, UN-05 |
| REQ-FUNC-033 | **listedAsFakeCompany:** the system shall match against the synced BMF list by VAT number, then FN, then normalized name; a name-only hit is never a definite match. | Listed company → TRUE with entry details; unlisted → FALSE; name-only hit → UNKNOWN / AMBIGUOUS_MATCH with the candidate entry. | M | T | UN-02, A4 |
| REQ-FUNC-034 | **onHfuList:** the system shall query the HFU web service with the partner's VAT number (`uidAuftragnehmer`) and the requesting organization's VAT number (`uidAuftraggeber`) and report the query date; the service has no lookup by name or FN, so there is no name fallback; the result is informational and FALSE is never presented as a failure. | Listed → TRUE; unlisted → FALSE with note "withholding applies"; service unavailable → UNKNOWN / SOURCE_UNAVAILABLE. | M | T | UN-02, BO-5 |
| REQ-FUNC-035 | **inCompanyRegister:** for Austrian partners the system shall look up the Firmenbuch by FN, or by name and VAT, and report FN, registered name and legal form. | Active → TRUE; deleted or not found → FALSE; several matches → UNKNOWN / AMBIGUOUS_MATCH. | M | T | UN-02 |
| REQ-FUNC-036 | **inBusinessLicenseRegister:** for Austrian partners the system shall look up GISA and list all active licenses with the responsible person. | Company with licenses → TRUE plus list; none → FALSE. | M | T | UN-02 |
| REQ-FUNC-037 | **hasRequiredLicenses:** if license codes are given, the result is TRUE only if each is active in GISA, otherwise FALSE naming the missing ones; without codes NOT_APPLICABLE. Which licenses are "necessary" is decided by the requester. | One missing license → FALSE naming it. | M | T | UC-04 |
| REQ-FUNC-038 | A partner counts as Austrian if its VAT number starts with "ATU" or an FN is given; for others, checks 033 and 035…037 return NOT_APPLICABLE. | German VAT without FN → 031, 032, 034 run; others NOT_APPLICABLE. | M | T | UN-06, A3 |
| REQ-FUNC-039 | Checks shall run in parallel and independently; the failure of one source shall never stop the others or the storing of the request. | GISA stubbed to fail → all other checks still TRUE/FALSE. | M | T | UN-05 |
| REQ-FUNC-040 | The system shall not re-check partners automatically, not even after a source sync; a re-check is a new request started by a user or client system and may reference the earlier request ID. | Advancing time or a sync creates no new result (code inspection and test). | M | I | R2 |
| REQ-FUNC-041 | Every request creates a new, distinct record; a later check never overwrites an earlier one. | Two checks of the same partner give two records with different timestamps. | M | T | UN-01 |
| REQ-FUNC-042 | A Request User shall be able to start a check through a web form with the same processing as the API. | Form and API give identical results for the same input. | M | D | UC-05 |

#### 3.2.5 Check Response

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-045 | The response shall contain request ID, received and completed timestamps (UTC), organization, requesting user's name, token name or "web" (never the token value), partner name, VAT number and one entry per check with value, reason, source, data timestamp and details (Appendix B). | Response validates against the JSON schema. | M | T | UC-04, UN-01 |
| REQ-FUNC-046 | The API shall return JSON by default and an HTML page with the same content if the `Accept` header prefers `text/html`; the HTML page shall be printable. | Same request with `Accept: text/html` shows every JSON field; print preview is readable. | M | T | UC-05, R2 |
| REQ-FUNC-047 | The response should contain `allChecksPassed`, true only if every applicable check has its expected value; `onHfuList` and NOT_APPLICABLE checks are ignored; UNKNOWN sets it to false. It is a convenience summary, not a decision. | Any deviating or UNKNOWN check sets it to false. | S | T | UN-02 |
| REQ-FUNC-048 | Every response and HTML page shall state that results are informational, that source data is not guaranteed complete or current, and that BizPartnerCheck carries no liability. | Disclaimer present in JSON and HTML. | M | I | BO-5 |
| REQ-FUNC-049 | Machine-readable values and reason codes shall be language-neutral; human-readable messages follow the user's language. | German user sees German messages with identical codes. | S | T | UN-07 |

#### 3.2.6 Evidence Log and Review
*Rationale:* customers must document and prove each check (R1, BO-2); requests are stored, documents are not (C7).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-050 | The system shall store every accepted request until deleted under REQ-FUNC-060: request ID, organization, requesting user, channel (web/API), token name, input, received/completed timestamps, all results with details, sync timestamps of the lists used, and any reference the source returns (e.g. VIES request ID). | Database record contains all fields, also for requests with UNKNOWN results. | M | T | UN-01, UN-10 |
| REQ-FUNC-051 | No role shall be able to modify stored results; a request can only be deleted as a whole. | No update path exists in UI or API. | M | I | UN-01 |
| REQ-FUNC-052 | Review Users and Org Admins shall be able to list the organization's requests, filter by date range, VAT number, company name, requesting user and result, and sort and page. | Filters return only matching requests. | M | T | UC-06 |
| REQ-FUNC-053 | The filtered list shall be retrievable as one report in JSON or HTML. | One call returns all matching requests. | M | T | UC-06, R2 |
| REQ-FUNC-054 | Review Users shall be able to open a request and see every stored detail, including who made it. | Detail page shows every stored field. | M | D | UC-06 |
| REQ-FUNC-055 | A Request User shall see status and results of own requests in the web app and via the API. | Request User sees own requests only. | M | T | UC-04, UC-05 |

#### 3.2.7 Housekeeping and Audit

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-060 | An Org Admin shall be able to delete one or many requests (selection or date filter) after confirmation; deletion is complete, with no soft delete or retention (backups expire per REQ-COMP-002). | Deleted request returns 404 and is gone from the database. | M | T | UC-07, UN-08 |
| REQ-FUNC-061 | The system shall audit, with actor and timestamp: logins (success and failure), user and role changes, token creation and revocation, every API request (including rejected ones), and deletions (count and date range only – never request content). | Each action creates exactly one audit entry. | M | T | UC-08, UN-01 |
| REQ-FUNC-062 | Org Admins shall be able to view and filter their organization's audit log. | Entries of other organizations never shown. | M | D | UC-08 |
| REQ-FUNC-063 | The Super Admin shall never see the content of an organization's check requests. | Inspection of all Super Admin screens. | M | I | UN-09 |

#### 3.2.8 Source Synchronization
*Rationale:* list sources change rarely and must not be fetched per request; the customer wants proof of when the lists were read (R2).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-070 | The system shall import the BMF fake-company RSS feed at least once per day. | Sync log shows one successful run per day. | M | D | UC-09 |
| REQ-FUNC-071 | The system shall query the HFU web service live per check; it shall import the list daily instead only if DLZ-AGH confirms a full-list export (REQ-POC-002, spike SCRUM-19: no export documented). | Decision documented; behaviour matches. | M | I | UC-09 |
| REQ-FUNC-072 | Every sync run shall be logged with source, start and end time, outcome, number of entries, and the feed's own publication or last-modified timestamp; the log is read-only for organizations. | One log row per run with all fields. | M | T | UN-10 |
| REQ-FUNC-073 | A failed sync shall keep the last good copy; if the last success is older than 48 h, list-based checks add `stale: true`. | Simulated failure keeps data; flag appears after 48 h. | M | T | UN-10 |
| REQ-FUNC-074 | The Super Admin should be able to view the sync log and start a sync manually. | Manual start creates a log row. | S | D | UC-10 |

#### 3.2.9 Additional Risk Checks (R3)
*Rationale:* beyond the mandatory checks the brief asks for person-based and financial risk (R1, slide 11), shown as detailed findings rather than a score (R2). Both depend on Firmenbuch and GISA access (A1).

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-FUNC-080 | **Person-based risk:** the system may report managers and owners (Firmenbuch) and license holders (GISA) of the partner who are also linked to a company on the fake-company list, with name, role and evidence. | Partner sharing a manager with a listed company → finding reported. | C | T | UC-11, UN-14 |
| REQ-FUNC-081 | **Financial risk:** the system may report equity, balance-sheet total and year of the latest Firmenbuch statement and flag negative equity or a missing statement. | Partner with negative equity → flagged. | C | T | UC-11 |
| REQ-FUNC-082 | Risk findings shall be separate response entries, never a score, and shall not change `allChecksPassed`. | Response has findings and no score field. | C | I | UC-11 |

### 3.3 Quality of Service
Targets marked (proposed) are starting points for confirmation by the customer (Appendix F).

#### 3.3.1 Performance and Scalability

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-PERF-001 | A check request shall complete within 10 s at p95 when all sources respond normally. | Load test with 100 requests against real sources. | M | T | BO-1 |
| REQ-PERF-002 | Checks against synced lists shall complete within 500 ms. | Timed lookups on the full data set. | M | T | FUNC-033 |
| REQ-PERF-003 | Web pages should show main content within 2.5 s (LCP) on broadband; listing 1,000 stored requests within 2 s. | Lighthouse and timed list query. | S | T | UC-06 |
| REQ-PERF-004 | The system shall sustain 200 check requests per minute across all tenants without errors other than 429. | Load test at 200 req/min for 5 min. | M | T | UN-12 |
| REQ-PERF-005 | The design shall support the customer's capacity estimate: 20,000 organizations, 100,000 users, 10,000 checks per day at peak (~3.7 million records per year), with stateless application instances and organization-indexed, paginated data. | Capacity analysis and schema review. | M | A | BO-4 |

#### 3.3.2 Security

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-SEC-001 | All traffic shall use HTTPS (TLS 1.2+) with HSTS; plain HTTP is redirected or refused. | TLS scan; HTTP call redirected. | M | T | C9 |
| REQ-SEC-002 | Passwords shall be stored only as salted hashes by Django's built-in password hashing (PBKDF2 or Argon2); API tokens shall have ≥ 256 bits of randomness and be stored only as SHA-256 hashes. | Database inspection shows no plaintext secrets. | M | I | C10, UN-04 |
| REQ-SEC-003 | The API shall allow at most 200 requests per minute per token, answering further requests with 429 and `Retry-After`; remaining quota is shown in response headers. | 201st request within a minute returns 429. | M | T | R2, UN-12 |
| REQ-SEC-004 | Login shall be blocked for 15 min after 5 failed attempts for the same account (counter in Django's cache). | 6th attempt refused even with correct password. | M | T | UN-04 |
| REQ-SEC-005 | All input shall be validated server-side against a schema; database access uses parameterized queries only. | Injection strings rejected or stored as plain text. | M | T | R11 |
| REQ-SEC-006 | Web sessions shall use Secure, HttpOnly, SameSite cookies, expire after 8 h of inactivity and protect state-changing forms against CSRF. | Cookie flags inspected; expired session leads to login. | M | T | R11 |
| REQ-SEC-007 | Logs and audit records shall never contain passwords, tokens or unnecessary personal data; access to them is restricted to authorized roles. | Log sample inspected; Request User cannot read logs. | M | I | C9 |
| REQ-SEC-008 | The application should be reviewed against the OWASP Top 10 before acceptance. | Checklist completed, no open high-severity findings. | S | A | R11 |

#### 3.3.3 Reliability

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-REL-001 | A failing or slow source shall only affect its own check (UNKNOWN / SOURCE_UNAVAILABLE); the request is still stored and answered. | Fault injection (timeout, error, invalid response) per source. | M | T | UN-05 |
| REQ-REL-002 | A failed sync shall never delete or corrupt the previously synced list. | Interrupted sync leaves the old list complete. | M | T | FUNC-073 |
| REQ-REL-003 | A transient source error (network error, HTTP 5xx) should be retried once within the 8 s budget. | Stub failing once, then answering → TRUE/FALSE. | S | T | INT-013 |
| REQ-REL-004 | A check request shall be stored atomically: the full request with all results, or nothing and a 500. | Simulated database failure leaves no partial record. | M | T | UN-01 |

#### 3.3.4 Availability

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-AVAIL-001 | The service should be available 99 % of each month (~7.2 h downtime), excluding outages listed on the hosting providers' status pages (proposed). | External uptime monitor report. | S | A | UN-12 |
| REQ-AVAIL-002 | Deployments shall cause no downtime and allow rollback to the previous version within 5 min. | Deploy during load test without failed requests; rollback shown. | M | D | CM-001 |
| REQ-AVAIL-003 | The database shall be backed up daily and be restorable to any point within the last 7 days. | Provider setting inspected; one test restore succeeds. | M | I | UN-01 |

#### 3.3.5 Observability

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-OBS-001 | Every log entry shall be structured (JSON) with timestamp, level, request ID (returned as `X-Request-Id`) and organization ID; logs are kept at most 30 days. | Log sample and retention setting inspected. | M | I | C9 |
| REQ-OBS-002 | The health endpoint shall report the status of the database and of each source, including success and timeout counts of the last 24 h. | Endpoint returns status per component. | M | T | UN-12 |
| REQ-OBS-003 | The team should be notified when a sync fails twice in a row or more than 5 % of requests in 15 min end with 5xx. | Simulated failures trigger the notification. | S | D | FUNC-072 |

### 3.4 Compliance

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-COMP-001 | The system shall store only personal data needed for the checks (user accounts, data returned by sources) and publish a privacy notice and a legal notice (Impressum) reachable from every page. | Data inventory matches the schema; notices linked on every page. | M | I | C9, UN-13 |
| REQ-COMP-002 | Personal data shall be deletable: deleting a request or organization removes its data completely; deleting a user removes account data while stored requests keep the requester's name as evidence; deleted data leaves backups after the 7-day window of REQ-AVAIL-003. | Query after deletion finds no data beyond what is specified. | M | T | C9, UN-08 |
| REQ-COMP-003 | Organizations shall accept terms of use at registration stating that BizPartnerCheck carries no liability and that the contracting decision remains with them; final wording is reviewed by the customer. | Registration impossible without acceptance. | M | D | BO-5 |
| REQ-COMP-004 | Each source shall be used only within its terms of use and open-data licence, including required attribution, reviewed before production integration. | Terms review recorded per source (REQ-INT-016). | M | I | SH-8 |
| REQ-COMP-005 | Database and application should be hosted in an EU region. | Provider region inspected (e.g. Frankfurt). | S | I | C9 |
| REQ-COMP-006 | Emails shall be transactional only (verification, invitation, password reset). | Email templates inspected. | M | I | C9 |

### 3.5 Design and Implementation
The ID prefix names the template subsection (INST 3.5.1 … CM 3.5.10). **Technology stack (C3):** Python and Django (templates for HTML pages, built-in authentication, admin, translations, ORM and migrations); PostgreSQL; `requests` and `feedparser` for the data sources; pytest and ruff; GitHub with GitHub Actions for CI, deployment after green builds and the daily sync trigger; the app on Render (Frankfurt), the PostgreSQL database on Neon (EU region) and email through Brevo's SMTP service. Further libraries are added only when a requirement needs them (e.g. a SOAP client if a source requires it). Distribution: one multi-tenant production deployment in one EU region, scaled automatically by the managed platform, on one domain registered by the team.

| ID | Requirement | Acceptance criteria | P | V | Trace |
|---|---|---|---|---|---|
| REQ-INST-001 | The system shall be deployable by configuration only, with every environment variable documented, and a developer should be able to run it locally with one command and a seeded test database. | A team member other than the original deployer deploys and runs it from the README. | M | D | C1, C3 |
| REQ-BUILD-001 | Every push shall run lint (ruff) and tests (pytest) in GitHub Actions; only green builds deploy; each pull request should get a preview deployment where the host supports it; merges need one review. | Failing build blocks deployment; PRs show approvals. | M | I | SH-7 |
| REQ-BUILD-002 | Dependencies shall be pinned in a lock file and use licences compatible with the project. | Lock file present; licence report clean. | M | I | SH-7 |
| REQ-MAINT-001 | Code shall follow a style guide enforced by a linter in CI; the README documents setup, architecture and API usage. | Linter in CI; README inspected. | M | I | SH-7 |
| REQ-MAINT-002 | Automated tests should cover at least 70 % of the lines of the check logic. | Coverage report ≥ 70 % for check modules. | S | A | FUNC-030…042 |
| REQ-MAINT-003 | Each source shall be accessed through its own adapter with a common interface, so a source or country is added or changed without touching the others; the adapters should be usable without the web app. | Adding a test source touches only its module and a registry. | M | I | BO-7 |
| REQ-PORT-001 | The system shall use standard PostgreSQL through the Django ORM and keep platform-specific settings in environment variables. | Runs unchanged against a PostgreSQL instance from a different provider. | M | I | C2, C3 |
| REQ-COST-001 | Operation during the project shall use free tiers; a paid service needs the customer's prior approval. | Provider billing shows no unapproved charges. | M | A | BO-4, A5 |
| REQ-DEAD-001 | Milestones: SRS 22.10.2026; POCs by 05.11.2026; MVP demo 17.12.2026; final delivery and presentation by 14.01.2027 (per course schedule). | Each milestone reached on its date. | M | I | BO-6, C11 |
| REQ-POC-001 | A POC shall show a successful VIES query and a parsed import of the BMF RSS feed, recording fields, limits and matching keys. | Live demonstration and POC note. | M | D | FUNC-031, 070 |
| REQ-POC-002 | A POC shall determine whether the HFU list can be downloaded in bulk. | Result documented; FUNC-071 decided. | M | D | FUNC-071 |
| REQ-POC-003 | A POC shall obtain access to GISA and Firmenbuch (access requests submitted by 22.10.) and show one successful lookup each. | One lookup per source demonstrated. | M | D | A1, C8 |
| REQ-CM-001 | Changes to this SRS shall be raised as issues, agreed with the customer, recorded as a new version in the Revision History with rationale and impact, and reflected in the traceability matrix and backlog. | Every change appears in the Revision History. | M | I | SH-1 |
| REQ-CM-002 | The API shall follow semantic versioning with a public changelog; breaking changes are announced at least 2 weeks ahead. | Changelog and announcement dates inspected. | M | I | INT-010 |

### 3.6 AI/ML
Not applicable. BizPartnerCheck contains no machine-learning components; all matching rules (e.g. name normalization in REQ-FUNC-032/033) are deterministic and documented, and name-only similarities always leave the final judgement to a person. Any future AI feature requires a change request (REQ-CM-001).

## 4. Verification
Every requirement is verified by the method in its V column. Each requirement REQ-[AREA]-[NNN] gets one verification record VR-[AREA]-[NNN] stored in the repository under `tests/` and run in CI where automated. Positive, negative, authorization, tenant-isolation and source-failure cases are always included. A requirement is accepted only when its acceptance criteria are met and the evidence is recorded.

| Method | Used for | Environment and tools |
|---|---|---|
| Test (T) | Functional logic, API, security controls, performance | Unit and integration tests in CI; end-to-end tests on staging; load-test tool; source stubs for fault injection |
| Demonstration (D) | User-visible flows, operations | Live demo to the customer on staging at the end of each sprint |
| Inspection (I) | Code, configuration, schema, documents | Review checklist, repository and database inspection |
| Analysis (A) | Measured targets over time | Uptime report, coverage report, capacity estimate, billing |

**Test data:** a valid Austrian and a valid German VAT number, an invalid VAT number, a company from the fake-company list, a company on and one not on the HFU list, a company with several business licenses, two test organizations with one user per role for isolation tests. No real customer data is used.

| Requirement group | IDs | Main method | Artifact | Status |
|---|---|---|---|---|
| Interfaces | REQ-INT-001…016 | T, I | tests/ui, tests/api, docs/sources | Planned |
| Registration, users, tenants, tokens | REQ-FUNC-001…024 | T | tests/e2e/registration, tests/integration/authz, tokens | Planned |
| Partner check, response, evidence, review | REQ-FUNC-030…055 | T, D | tests/integration/checks + source stubs, tests/e2e/review | Planned |
| Housekeeping, audit, synchronization | REQ-FUNC-060…074 | T, D, I | tests/integration/audit, sync | Planned |
| Risk checks | REQ-FUNC-080…082 | T, I | tests/integration/risk | Optional (R3) |
| Quality of service | REQ-PERF, SEC, REL, AVAIL, OBS | T, A, D | tests/load, security, faults; OWASP checklist; uptime and restore reports | Planned |
| Compliance and design | REQ-COMP, INST … CM | I, D, A | data inventory, CI configuration, POC notes | Planned |

## 5. Appendixes

### Appendix A – Permission Matrix
Binding for REQ-FUNC-012. Rights are limited to the user's own organization (except Super Admin); roles add up.

| Action | Super Admin | Org Admin | Request User | Review User |
|---|:-:|:-:|:-:|:-:|
| Create, deactivate, delete organizations | ✓ | | | |
| Manage users and roles | | ✓ | | |
| Create and revoke own tokens | | ✓ | ✓ | ✓ |
| Create and revoke any token of the organization | | ✓ | | |
| Start a check (web or API) | | | ✓ | |
| View own requests | | ✓ | ✓ | ✓ |
| View all requests of the organization | | ✓ | | ✓ |
| Delete requests | | ✓ | | |
| View audit log | | ✓ | | |
| View sync log; start manual sync | ✓ | | | |
| View check request content | ✗ | ✓ | own | ✓ |

### Appendix B – Example Check Response (JSON)
Informative; the normative schema is part of the OpenAPI document (REQ-INT-015).

```json
{
  "requestId": "c1f0a7e2-5d1b-4b7e-9a10-3e2f6b8d9c41",
  "receivedAt": "2026-11-18T09:42:09Z", "completedAt": "2026-11-18T09:42:13Z", "organization": "Beispiel Bau GmbH",
  "requestedBy": { "user": "Anna Beispiel", "channel": "api", "tokenName": "ERP prod" },
  "partner": { "companyName": "Muster Bau GmbH", "vatNumber": "ATU12345678", "companyRegisterNumber": "123456a" },
  "checks": [
    { "check": "vatValid", "result": "TRUE", "source": "VIES", "dataTimestamp": "2026-11-18T09:42:12Z" },
    { "check": "nameMatchesVat", "result": "TRUE", "source": "VIES" },
    { "check": "listedAsFakeCompany", "result": "FALSE", "source": "BMF", "dataTimestamp": "2026-11-18T03:00:04Z", "stale": false },
    { "check": "onHfuList", "result": "FALSE", "source": "OEGK", "dataTimestamp": "2026-11-18T03:05:41Z", "details": { "withholdingApplies": true } },
    { "check": "inCompanyRegister", "result": "TRUE", "source": "Firmenbuch", "details": { "fn": "123456a", "legalForm": "GmbH" } },
    { "check": "inBusinessLicenseRegister", "result": "UNKNOWN", "reason": "SOURCE_UNAVAILABLE", "source": "GISA" },
    { "check": "hasRequiredLicenses", "result": "NOT_APPLICABLE" }
  ],
  "allChecksPassed": false,
  "disclaimer": "Informational only; source data is not guaranteed complete or current. BizPartnerCheck carries no liability; the contracting decision remains with the customer."
}
```

### Appendix C – Reconciled Statements and Draft Decisions
The customer notes and the four individual drafts contained overlapping or contradictory statements. Each was resolved as follows; the customer confirms them at sign-off.

| ID | Statements | Resolution in this SRS |
|---|---|---|
| C-01 | "Two types of users" vs. "four user types" | Four roles: Super Admin, Org Admin, Request User, Review User; roles are additive (2.5) |
| C-02 | "Admin creates request user and a token for the user" vs. tokens "up to the user" | Org Admin creates tokens for any user; users may create their own; tokens carry the owner's rights (FUNC-020/021) |
| C-03 | Customer listed address, first/last name, organization name and VAT number as data "the company should provide" | This is the registering organization's data (FUNC-001); a partner check needs VAT number and name, the rest is optional (FUNC-030) |
| C-04 | "A field for each check which is a boolean" vs. "TRUE, FALSE, perhaps INVALID / NO DETAILS FOUND" | Each check is a yes/no question with TRUE/FALSE, plus UNKNOWN with reason and NOT_APPLICABLE, and a stated expected value (3.2.4) |
| C-05 | Drafts treated HFU "not listed" as a failure | Customer feedback: not being listed is normal and means withholding; HFU is informational and excluded from `allChecksPassed` (FUNC-034, 047) |
| C-06 | "Registration not immediate priority" vs. "register button, free sign-up with email verification" | Organization self-registration is Must; individual user self-registration is Won't (FUNC-001, 005) |
| C-07 | "Not a periodic check" vs. "rechecks" and daily RSS polling | No automatic re-checks; the daily job only refreshes source lists (FUNC-040, 070) |
| C-08 | "Don't store documents" vs. "must prove" | Store structured request records and timestamps, never documents (FUNC-050, C7) |
| C-09 | "Full delete, no retention" vs. proof of technical actions | Requests are deleted completely; only a content-free audit entry of the deletion remains (FUNC-060/061) |
| C-10 | "If one thing fails the company shouldn't do business" vs. "it is up to them" | Detailed result per check and a non-binding summary, never a decision (FUNC-047/048) |
| C-11 | Austria only vs. all EU | VAT check for all EU; national checks for Austria; others NOT_APPLICABLE (FUNC-038) |
| C-12 | Drafts differed on password storage vs. using an external identity provider | Django's built-in authentication stores salted password hashes; no self-built credential code and no external identity provider (C10, SEC-002) |
| C-13 | Drafts differed on the delivery plan (increments to 27.01. vs. course roadmap) | The course roadmap with sprints to 14.01.2027 is binding (2.8, DEAD-001) |

### Appendix D – Customer Questions and Where They Are Answered

| # | Question (R2) | Answer / where |
|---|---|---|
| 1 | Who uses the system, which roles? | Four roles, additive – 2.5, Appendix A |
| 2 | Most important checks for the MVP? | VAT, fake company, HFU, company register, business-license register – 3.2.4 |
| 3 | VIES for Austria only or all EU? | All EU for VAT; ~80 % Austrian – FUNC-031, 038 |
| 4 | How to match against the lists? | Fake-company list: VAT, then FN, then name; name-only = AMBIGUOUS_MATCH – FUNC-033. HFU: by VAT number only – FUNC-034 |
| 5 | Data needed from Firmenbuch / GISA; paid access? | Status, FN, managers, licenses; operator credential via ID Austria – 3.1.3, C8 |
| 6 | What if a source is unavailable? | UNKNOWN / SOURCE_UNAVAILABLE, others continue – FUNC-039, REL-001 |
| 7 | Which systems use the API? | Customers' ERP / procurement software – 2.2, UC-04 |
| 8 | Token permissions and validity? | Owner's rights; valid until revoked – FUNC-020…023 |
| 9 | What must be stored as proof? | Timestamps, requester, input, results, sync dates – FUNC-050 (OD-02) |
| 10 | Export, e.g. PDF? | No PDF; JSON and printable HTML report – FUNC-046, 053 |
| 11 | Risk as warning or score? | Detailed findings, never a score – FUNC-082 |
| 12 | Meeting frequency, project success? | Feedback each sprint; success = working documented workflow – 2.1, OD-04 |

### Appendix E – Traceability Matrix
Each user need traces back to a business objective and forward to use cases and requirements; every requirement also names its trace in its own row.

| User need | BO | Use cases | Requirements |
|---|---|---|---|
| UN-01 Proof of checks | BO-2 | UC-06, UC-08 | FUNC-041, 045, 050…054, 061; REL-004; AVAIL-003 |
| UN-02 One-step check | BO-1 | UC-04, UC-05 | FUNC-030…037, 042, 047; PERF-001, 002 |
| UN-03 Integration | BO-3 | UC-03, UC-04 | FUNC-020, 046, 055; INT-010…015 |
| UN-04 Access control | BO-3 | UC-02, UC-03, UC-08 | FUNC-010…012, 021…023, 062; SEC-002, 004 |
| UN-05 Clear result per check | BO-1, BO-5 | UC-04, UC-05 | FUNC-032, 039, 048; INT-005, 013; REL-001, 003 |
| UN-06 EU partners | BO-1 | UC-04 | FUNC-031, 038 |
| UN-07 German and English | BO-4 | all UI use cases | INT-001, 002; FUNC-049 |
| UN-08 Complete deletion | BO-2 | UC-07 | FUNC-060; COMP-002 |
| UN-09 Tenant isolation | BO-4 | UC-02 | FUNC-012, 013, 063; SEC-007 |
| UN-10 Data freshness | BO-2 | UC-06, UC-09 | FUNC-050, 070…073 |
| UN-11 Free self-service start | BO-4 | UC-01 | FUNC-001…004; INT-003; COMP-003 |
| UN-12 Stable, cheap operation | BO-4 | UC-10 | FUNC-005, 014, 074; PERF-004, 005; SEC-003; OBS-002; COST-001 |
| UN-13 Lawful data processing | BO-4 | – | COMP-001, 002, 005, 006; OBS-001 |
| UN-14 Hidden risk | BO-7 | UC-11 | FUNC-080…082 |

BO-6 (workflow on time) is covered by REQ-DEAD-001, REQ-POC-001…003 and the apportioning in 2.8.

### Appendix F – Open Decisions and Risks

| ID | Decision or risk | Affects | Owner |
|---|---|---|---|
| OD-01 | Is a name-only match on the fake-company list acceptable as UNKNOWN / AMBIGUOUS_MATCH? | FUNC-033 | Customer |
| OD-02 | Which fields must a stored request contain to count as legal proof? FUNC-050 is the proposal. | FUNC-050 | Customer |
| OD-03 | Which GISA trade codes count as "necessary licenses", or does the caller always supply them? | FUNC-037 | Customer |
| OD-04 | Meeting rhythm (proposed: end of every sprint) and final acceptance date. | A6, DEAD-001 | Customer and team |
| OD-05 | HFU: the web service documentation shows no full-list export; DLZ-AGH was asked on 04.11.2026 and the reply is pending. BMF feed: exact fields (VAT present?) still to confirm. | FUNC-071, A4 | Team (POC-001/002, SCRUM-19) |
| OD-06 | Access via ID Austria (risk to R1): Maryam Salem holds the ID Austria login; the GISA application was submitted on 04.11.2026; the Firmenbuch request and the approval times are still open (SCRUM-20). | A1, POC-003 | Team |
| OD-07 | Proposed QoS targets (availability, response times) and capacity figures to be confirmed. | 3.3 | Customer |
| OD-08 | **Closed 2026-11-04:** app on Render, database on Neon, email via Brevo (SCRUM-42). Remaining: the Brevo sender is temporarily Luka Herceg's private email address and must be changed to a team email address, later one on the team's own domain. | C3, A5, COST-001 | Team |
| OD-09 | Final wording of the no-liability terms and legal basis for processing register person data (GDPR). | COMP-001, 003 | Customer, legal advice |
| RK-01 | Only 6–10 h/week per person | All | Mitigation: release plan and fallback roles (2.8) |
| RK-02 | External services unavailable or changed | FUNC-031…037 | Mitigation: adapters, UNKNOWN state, last-good snapshots |

### Appendix G – Sign-off
This SRS becomes the agreed requirements baseline once the customer and the project team have reviewed the open decisions and approved scope and acceptance criteria.

| Role | Name | Signature | Date |
|---|---|---|---|
| Customer | | | |
| Product Owner (project team) | | | |
| Reviewer / instructor (if required) | | | |
