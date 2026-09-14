# AtlasOne

Academic planning should not depend on already knowing how the school system works.

AtlasOne is a Django academic-planning prototype that helps high school students understand their graduation requirements, make informed course requests, and bring their families into the conversation. It is designed with students in lower-income communities and families of immigrant backgrounds in mind, particularly those navigating unfamiliar school terminology, language barriers, or limited access to individualized guidance.

The goal is to make academic information easier to understand and act on—not to replace a school counselor. Optional AI-powered translation and built-in parent text-to-speech offer additional ways to ask questions and understand a student's progress.

Try the local demo with fictional records and no API key. Graduation calculations and prerequisite checks run in Python, independently of the language model; Gemini is optional for conversational explanations, translation, and speech.

![Student dashboard with fictional data](docs/screenshots/student-dashboard.png)

## Making the next step understandable

Terms such as *earned credits*, *core requirements*, and *prerequisites* are useful only when students know what they mean for their own choices. AtlasOne brings those requirements together with a student's transcript so the next conversation can begin with a specific question: "What do I still need, and which classes can I take next?"

- **For students:** See graduation progress, identify missing requirements, and request courses with prerequisite checks. The planner distinguishes completed work from courses still in progress, including next-year choices that depend on passing a current class.
- **For parents and guardians:** View only explicitly linked students, ask for plain-language explanations, and use translation or audio to engage with academic information in a more useful format.
- **For counselors:** Review course requests, maintain transcripts, and exchange messages with students and linked families. The application supports these conversations rather than making final scheduling decisions.

This is an accessibility-focused design direction, not a claim of proven educational outcomes. Evaluation with students, families, and schools is an important next step for validating whether these features meet their needs.

## Translation and read-aloud support for families

Understanding a graduation report involves more than translating individual words. Families may also need an explanation of how credits, required subjects, and course sequences fit together.

With Gemini enabled, students can request parent-friendly translations of academic guidance. The parent advisor is instructed to explain school terms in plain language, respond in the parent's language unless another is requested, and suggest practical next steps based on the linked student's record.

Example questions to try:

- "Explain my graduation progress for my parents in Spanish, and explain what credits mean."
- "What is a prerequisite, and why does it matter for my next classes?"
- "Explain my student's remaining requirements in Portuguese. What should we ask the counselor?"

The parent chat also includes a **Read responses out loud** option and a voice selector. Its built-in text-to-speech integration requests an audio version of the response from Gemini and plays it in the browser. This gives parents who prefer listening another way to engage with the explanation, including translated responses where supported by the provider.

The two operating modes have different capabilities:

| Capability | Local demo, no API key | Gemini enabled with your own key |
| --- | --- | --- |
| Graduation calculations and prerequisite checks | Available | Same Python-based rules |
| Academic explanations | Rule-based recommendations and summaries | Conversational explanations using academic context |
| Translation | Limited preset text in English, Spanish, French, and Portuguese; some academic details remain in English | Requested-language explanations, subject to model support and quality |
| Parent text-to-speech | Disabled | Optional provider-generated audio with voice selection |

The local fallback is not a general-purpose translator, and speech requires a working provider connection. Translation accuracy, pronunciation, and language coverage need human review; important decisions should be confirmed with the school. Browser autoplay restrictions may also prevent audio playback.

## Try it locally

Requires Python 3.12–3.14 and Git. Python 3.14 is the locally verified version; CI also targets 3.12.

Clone this repository, open its directory, then create an environment:

```powershell
# Windows PowerShell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Generate a local signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Paste that value after `DJANGO_SECRET_KEY=` in `.env`. Keep the key local. The example selects `demo.sqlite3`, so the demo does not use an existing `db.sqlite3`. Existing environment variables take precedence over `.env`.

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open [localhost:8000](http://127.0.0.1:8000). All three fictional accounts use the local-only password `AtlasDemo!2026`:

| Account | What to explore |
| --- | --- |
| `demo.student` | Graduation progress, conditional prerequisites, course requests |
| `demo.counselor` | Pending requests, transcript entry, student messaging |
| `demo.parent` | Linked student's progress, family-facing explanations, and optional translation/read-aloud support |

`seed_demo` refuses production mode and an existing non-demo database. Running it again preserves the demo's records and passwords. It creates no administrator account.

## Walk through a student's next steps

1. Sign in as the student. Geometry is **in progress**, so it does not count as completed credit.
2. Open the planner. Algebra II depends on passing Geometry; its pending request is already seeded. Request Chemistry, whose Biology prerequisite is complete.
3. Sign out and sign in as the counselor. Review the request, add a note, and inspect the student's transcript.
4. Sign in as the parent. Only the explicitly linked student is visible. Open the advisor for a local summary, or ask for an explanation in Spanish to explore the limited translated fallback.
5. Optionally enable Gemini using the instructions below. Ask the parent advisor to explain the student's remaining requirements in the parent's preferred language, then enable **Read responses out loud** and send another question to try text-to-speech.

[Planner screenshot](docs/screenshots/planner.png) · [Counselor screenshot](docs/screenshots/counselor-dashboard.png) · [Parent screenshot](docs/screenshots/parent-dashboard.png)

## Technical design

The application separates academic rules, access control, and AI-generated explanations. A model response does not determine earned credits or course eligibility.

- **Access rules:** `Pathway/access.py` scopes students and conversations before records are fetched. Counselors see their district or explicit assignments. Parent access requires a current link.
- **Academic policy:** `Pathway/services/academic_policy.py` is the shared passing/in-progress policy. The planner permits conditional next-year requests; the advisor distinguishes these from immediately eligible courses.
- **Graduation estimate:** `Pathway/services/graduation.py` combines subject-credit gaps, required courses, prerequisite traversal, and a heuristic capacity estimate.
- **AI boundary:** `Pathway/services/snapshot.py` builds academic context. `Pathway/services/gemini.py` handles HTTP, response-size limits, and speech conversion. `Pathway/services/advisor_reply.py` keeps provider-failure status separate from conversational text.
- **HTTP and forms:** `Pathway/views/` is grouped by workflow. Django forms validate signup, transcripts, and messages; multi-record signup and transcript imports use transactions.

See [architecture and tradeoffs](docs/architecture.md) for the assumptions behind these choices.

## Verification

```bash
python -m ruff check .
python -m ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python -m coverage run manage.py test
python -m coverage report
python -m pip_audit --local
python scripts/check_publication.py
```

GitHub Actions runs lint, formatting, tests, migration checks, demo setup, static collection, production-setting checks, and dependency auditing. The workflow uses read-only permissions and pinned action commits. Dependabot checks Python dependencies and Actions weekly.

Direct dependencies are pinned in `requirements.txt`; `constraints.txt` records the verified runtime dependency set. Update related pins together and rerun the checks.

## Enable AI translation and parent text-to-speech

Keep `AI_ENABLED=False` for the offline demo. To exercise conversational translation and the parent read-aloud integration, add your own Gemini API key to the local `.env` file:
```dotenv
AI_ENABLED=True
GEMINI_API_KEY=your_own_gemini_api_key
```

Restart the Django server after changing these settings. Model names are configurable through `GEMINI_MODEL` and `GEMINI_TTS_MODEL`. Every person running a downloaded copy can supply their own key; no shared project key is required. Keep real keys out of source code and Git—`.env` is ignored, while `.env.example` documents the configuration. Requests use the key owner's provider quota and may incur charges.

Enabling this sends academic context and messages to Google. Use fictional data. Provider credentials, availability, translation quality, and speech generation are not verified by the offline test suite; HTTP interactions are mocked. Text errors fall back to local recommendations.

If an attempted advisor request fails, that reply gets an "AI service unavailable" notice. Successful replies, deliberately disabled AI, and a missing API key do not trigger this failure notice. Speech failures are reported separately from text-generation failures. The notice is rendered in the browser from an `api_failed` response flag, never appended to the answer or sent in Gemini's conversation context.

The explicit connection test `python -m Pathway.utils.api_tester` makes a provider request using a generic prompt with no student records. It may consume quota.

## Scope and limitations

This is a portfolio prototype, not a school deployment. Accessibility is a goal that still needs validation: keyboard and screen-reader testing, multilingual interface review, and usability studies with students and families are needed. AI translation does not mean the entire interface is localized, and this project does not claim WCAG conformance or certified translation quality.

The application has no verified invitation workflow, distributed rate limiting, background job queue, or audit trail. SQLite is the default. Credits use legacy floating-point fields; repeated transcript rows and district-specific repeat-credit rules need further modeling. The graduation engine estimates feasibility; it is not an optimal timetable solver.

Parent and counselor accounts must be provisioned by staff. For manual local administration, create a superuser with `python manage.py createsuperuser`, then create a User and its role profile through `/admin/`. Link parents and assign counselors explicitly.

PDF import supports a particular five-column table layout, not arbitrary transcripts or OCR. Its size/page limits do not make parsing untrusted documents safe for public hosting.

Read [security and known limitations](SECURITY.md).