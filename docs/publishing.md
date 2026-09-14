# Publish the portfolio on GitHub

The local repository has been initialized on `main`. No remote repository, commit, or push was created during preparation.

## 1. Review what will be public

Replace any previously exposed credentials through their owners before publishing. Keep the working `.env`, all databases, and real transcripts private.

From the activated environment:

```bash
git status --short
python scripts/check_publication.py
git check-ignore .env db.sqlite3 demo.sqlite3
```

The publication check scans tracked and unignored files for private paths and a few common credential patterns. It is not a complete secret audit. Inspect the file list and screenshots yourself. The supplied screenshots contain only the seed command's fictional records.

If this capstone involved teammates or assets supplied by someone else, add accurate attribution and describe your contribution. Choose a license before encouraging reuse; no license was selected automatically.

## 2. Run the same checks as CI

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python -m coverage run manage.py test
python -m coverage report
python -m pip_audit --local
```

Reproduce the demo in a fresh directory or clone before relying on the quickstart. Do not copy your database or .env into that check.

For a production-settings exercise in PowerShell:

```powershell
$env:DJANGO_DEBUG = "False"
$env:DJANGO_ALLOWED_HOSTS = "example.com"
$env:DJANGO_HSTS_INCLUDE_SUBDOMAINS = "True"
$env:DJANGO_HSTS_PRELOAD = "True"
python manage.py check --deploy --fail-level WARNING
Remove-Item Env:DJANGO_DEBUG, Env:DJANGO_ALLOWED_HOSTS, Env:DJANGO_HSTS_INCLUDE_SUBDOMAINS, Env:DJANGO_HSTS_PRELOAD
```

This checks configuration under an illustrative all-HTTPS domain. It does not deploy the app. HSTS coverage of subdomains/preload should be chosen for the actual hosting domain, not copied blindly.

## 3. Make the first commit

Set your Git author identity if it is not configured. A GitHub noreply email is an option if you prefer not to expose your personal address.

```bash
git add .
git diff --cached --stat
git diff --cached --name-only
python scripts/check_publication.py --tracked
git diff --cached --check
git commit -m "Prepare AtlasOne portfolio demo with scoped access and regression tests"
```

Read the staged changes before committing. No requirement exists to invent an incremental history for work already done. Make future changes in focused commits that explain a concrete behavior change.

## 4. Create the GitHub repository and push

Create an empty repository on GitHub named `atlasone` (or your preferred name). Avoid initializing it with a second README. Start private if you want to review CI and the rendered README before making it public.

Copy the repository's actual HTTPS or SSH URL, then run:

```bash
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

`YOUR_REPOSITORY_URL` is the one placeholder in those commands; replace it with the URL GitHub gives you.

In GitHub, inspect the Actions run. Local validation does not imply the hosted matrix has passed. Resolve failures before featuring the repository.

## 5. Make the repository easy to evaluate

- Set the description to: “Django academic-planning prototype with role-scoped access, prerequisite checks, transcript review, and an offline demo.”
- Use relevant topics such as `django`, `python`, `education`, `portfolio`, and `role-based-access-control`.
- Enable available secret scanning/push protection, dependency alerts, and private vulnerability reporting. Check the Security settings; features vary by repository/account.
- Require the Checks workflow on the default branch where your repository settings support it.
- Pin the repository on your profile. Add a 60–90 second demo video if useful: student progress → conditional request → counselor review → linked-parent view.
- Replace generic resume claims with what is demonstrable: the authorization policy, offline reproducibility, and regression cases. Explain which decisions were yours and where assistance was used.

See [GitHub's secret-scanning documentation](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning) and [the official checkout action](https://github.com/actions/checkout) for the publishing infrastructure.

## 6. Keep code publication separate from hosting

GitHub Pages does not run a Django backend. Publishing source is enough for this local portfolio demo. Public hosting needs a production app server, HTTPS, configured static files, deployment secrets, persistence/backups, and the open security work in [SECURITY.md](../SECURITY.md).

Do not expose the development server, enable debug mode on the Internet, deploy the public demo passwords against real records, or describe this prototype as ready for school use.
