# Architecture and tradeoffs

## Request boundaries

```text
Browser → Django view → scoped query / validated form → database
                     → academic services → local result
                                         → optional Gemini transport
```

Authentication identifies the account; it is not enough to authorize access to a student. Views call the shared access functions before fetching transcripts, requests, or message threads.

| Role | Allowed records |
| --- | --- |
| Student | Own academic record; counselors in the same district or explicitly assigned |
| Counselor | Students in the same district or explicitly assigned to that counselor |
| Parent | Students with a current ParentStudentLink |
| Parent/counselor conversation | Current parent link and current assigned counselor |

Existing conversations do not preserve access after a transfer or removed relationship. Access tests exercise both reads and writes. The same-district counselor rule is a prototype policy; a real school may need assignment-only access.

## Academic policy

A passing row has a grade of at least 60 and positive earned credits. A row with zero grade and zero credits in the student's current grade is treated as in progress. That sentinel is inherited from the original model; it should eventually become an explicit enrollment status.

Next-year requests can depend on in-progress prerequisites, provided the student passes them. Immediate advisor eligibility requires completed prerequisites. The UI labels conditional requests accordingly.

Graduation estimation traverses prerequisites and detects cycles, then chooses courses to address credit gaps and required core classes. Capacity is estimated from grade level, transcript history, and catalog size. The result does not model terms, instructor availability, conflicting periods, prerequisites across multiple years, or an optimal minimum schedule. The legacy payload key `minimum_courses_needed` is an estimate; the UI says so.

Completion combines earned subject credits and completed required courses. In-progress courses influence future feasibility but do not inflate completion.

## Why these boundaries

- Django forms replace ad hoc password and field validation. User/profile/transcript creation is atomic so failed signup leaves no partial account.
- PDF extraction returns proposed rows for counselor review. Unknown numbers remain blank; a rejected or oversized document is not partially accepted.
- The planner is computed once per request and passed into the request form. Snapshot scoring uses indexed lookups instead of scanning subject totals for each candidate.
- The transport layer limits text output, downloaded bytes, and socket timeouts. Speech makes one attempt. These limits reduce cost and latency but do not replace a queue or request quotas.
- Ordinary workflow tests run without a provider key. Separate transport tests verify headers, output limits, malformed responses, and audio wrapping.

## Deliberate remaining debt

Model field names retain the original camelCase schema to avoid a broad rename migration solely for style. A later schema change should introduce DecimalField credits, explicit enrollment/attempt records, repeat-credit rules, and database constraints together.

Views are separated by workflow, but the counselor module and graduation algorithm are still sizeable. Some pages still create empty transcript/conversation records lazily on read. Extract those workflows when introducing explicit conversation creation and audit events.

The refreshed sign-in and student dashboard use external CSS. Older counselor/parent pages still duplicate inline styling. A shared page layout and navigation component are the next presentation refactor; replacing them should include keyboard and mobile checks.
