# Verification record

Verified locally on 2026-09-11 using Windows and Python 3.14 in a newly created `.venv-portfolio` environment. The original virtual environment and existing `db.sqlite3` were preserved.

| Check | Result |
| --- | --- |
| Django test suite | 51 tests passed |
| Coverage | 77% combined statement/branch coverage across configured application code |
| Ruff lint and formatting | Passed |
| Django system checks | Passed |
| Migration drift | None |
| Package compatibility | `pip check` passed |
| Vulnerability audit | No known vulnerabilities reported for the verified installed environment |
| Clean-copy demo | All migrations, initial seed, repeat seed, and static collection passed without copying .env or databases |
| Production-setting checks | Passed with an explicit strong key, hosts, and HSTS options |
| Publication guard | No listed private paths or credential patterns found among publishable files |

The browser walkthrough covered student sign-in, progress labels, next-year conditional prerequisites, counselor dashboard, parent linked-student view, and an actual offline parent-advisor response. That walkthrough found and fixed a frontend/API mismatch in the JSON student ID.

The screenshots in this directory's `screenshots/` folder were captured from the running app with fictional seed records, not generated mockups.

Not established by this verification:

- The GitHub-hosted CI matrix has not run; no remote repository was created or pushed.
- A live Gemini text/TTS call was not made. Transport behavior is tested with mocked HTTP responses.
- Previously exposed credential revocation has not been verified.
- This was not a penetration test, production load test, or full accessibility/mobile audit.
- The publication guard does not prove that arbitrary secrets or personal data are absent from every file or old copy.

Coverage excludes migration files, tests, and admin registration code. The seed command's successful path was exercised separately by the clean-copy check and is not included in the measured test coverage. Coverage is a diagnostic result, not a security score.
