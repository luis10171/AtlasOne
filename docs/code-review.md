# Portfolio code review

Review date: 2026-09-11.

## Findings addressed

| Finding | Why a reviewer would care | Change |
| --- | --- | --- |
| Django 6.0.1 pin predates security fixes | Known framework vulnerabilities undermine security claims | Upgraded within the 6.0 series to 6.0.8; updated PDF dependencies and added auditing |
| Public role signup could be re-enabled by a flag | Knowing a student username must not grant parent access | Removed the insecure enrollment paths; staff provisioning only |
| Old conversation IDs retained access after a transfer | Checking a role at login does not authorize every later record | Current district, assignment, and parent links are checked on message access |
| JSON arrays and invalid IDs could produce 500s | A demo fails on ordinary malformed input | Shared schema/type/size validation before database or provider work |
| Signup used hand-written password rules and multiple independent writes | Configured validators were bypassed; partial accounts were possible | Django UserCreationForm and atomic account creation |
| Planner used 65 as passing; other services used 60 | A student could be eligible in one screen and blocked in another | Shared academic-policy functions with boundary tests |
| Unknown PDF grades became zero; long documents were truncated | Missing information looked authoritative or silently disappeared | Blank values require review; whole documents are rejected over the limit |
| Keys in request URLs; long speech retries | URLs can leak into logs; retries tie up request workers | Header-based credentials, response limits, single speech attempt |
| Runtime signing key changed on each restart; example .env was not loaded | Sessions and setup behaved unpredictably | Required stable signing key, dotenv loading, production fail-closed checks |
| Dashboard showed in-progress rows as zero grades and counted ongoing core classes as complete | Presentation disagreed with academic meaning | Explicit in-progress labels and completion based on completed work |
| No reproducible showcase | A recruiter had to invent accounts and data | Empty-database seed command, offline mode, screenshots, and walkthrough |

Previously exposed credential validity and revocation could not be established. Credential rotation remains an owner action.

## Code that looked unreviewed

Source appearance cannot establish whether code was AI-generated. The signals here were inconsistency and missing engineering decisions:

- Comments narrated syntax: “individual student model used to store every individual student,” separator banners, and “Safety check (always good practice).” Removed these and kept comments explaining policy or tradeoffs.
- The 1,200-plus-line views file combined authentication, transcript imports, AI, parents, counselors, and authorization. Split it into workflow modules and a shared access module.
- Several signup handlers repeated subtly different validation; two messaging forms repeated the same participant setup. Consolidated the common behavior.
- A commented-out upload form and obsolete signup templates looked like abandoned experiments. Removed them.
- Exception handling swallowed database failures and returned empty transcripts. Academic queries now naturally return empty querysets when records are absent, while actual database failures remain visible.
- A hard-coded AP Biology suggestion referred to a course that might not exist. Replaced it with a catalog-independent question.
- Fixed graduation-year bounds would expire. Signup now validates against the current year.
- Student transcript rendering repeatedly fetched course records. The view now joins courses once; snapshot scoring uses dictionary and set lookups.
- No consistent formatting or import policy existed. Ruff configuration and CI make those choices repeatable.

No effort was made to disguise AI assistance. A stronger portfolio shows that the author can explain the access policy, reproduce failures, test boundaries, and identify where the design stops being reliable.

## Remaining work ranked by impact

1. **Before any public service:** verified invitations/guardian links; rate limits for login/signup/chat/uploads; provider budgets; isolated PDF processing; audit logging and data retention.
2. **Before real academic use:** district-specific passing rules, explicit course attempts/enrollment state, repeat-credit handling, DecimalField credits, and database constraints. The current model permits duplicate rows and simplistic credit totals.
3. **For growth:** background tasks, PostgreSQL, pagination, query-count budgets, caching with deliberate invalidation, and review-transition concurrency controls.
4. **For a stronger presentation:** shared counselor/parent layouts, broader keyboard/mobile checks, a short narrated demo, and a few focused issues tied to the above tradeoffs.
5. **For ownership:** document your actual contribution, attribute teammates and assets where applicable, and select a license you are entitled to grant. Do not claim benchmarks, users, or production deployment without evidence.
