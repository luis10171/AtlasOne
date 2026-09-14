# Security scope

AtlasOne is a portfolio prototype intended for fictional data on a local machine. Passing automated checks is not evidence of production readiness or educational privacy compliance.

## Before publishing

An earlier source version contained a Django signing key and a Gemini credential-shaped literal. Their validity was not established. Treat them as exposed: replace the signing key and revoke or rotate the provider credential through its owner. Removing a literal does not revoke a credential or erase old copies.

Do not publish databases, transcripts, real student information, .env files, private keys, IDE state, or environment directories. The ignore rules and publication check help detect these mistakes. The check is intentionally limited and does not scan historical commits.

## Current protections

- Public counselor and parent signup cannot grant roles or links.
- Access scopes cover records and existing message conversations.
- Django CSRF protection stays enabled; signup uses configured password validators.
- Production defaults require explicit hosts and a long signing key. HTTPS redirect and secure cookies are enabled outside debug mode.
- Gemini keys travel in request headers, not URLs. External AI is opt-in.
- Advisor JSON is validated before provider calls. PDF files and formsets have explicit size/count limits.

## Open deployment blockers

1. **Identity and access lifecycle:** staff provisioning is manual; no verified invitations, guardian verification, assignment audit, or robust district enrollment workflow exists.
2. **Abuse and cost controls:** login, signup, chat, and uploads lack distributed rate limits. Add gateway/application quotas, budget controls, and concurrency limits before exposing them publicly.
3. **PDF isolation:** page/byte limits are not protection from every decompression or CPU attack. Parse in a worker with memory/time limits and validate files at the ingress layer.
4. **Data integrity:** numeric model fields lack comprehensive database constraints; duplicate transcript rows can inflate credits. Repeat attempts, GPA rules, and district requirements need explicit modeling.
5. **Student data handling:** AI sends academic records and user messages to a third party when enabled. There is no consent workflow, redaction guarantee, retention policy, or auditable access history.
6. **Operations:** no production database, backup/restore drill, background queue, shared throttling backend, metrics, or incident response has been configured.

HSTS subdomain coverage and preload are intentionally explicit environment options. Enable them only for a domain whose subdomains support HTTPS. The CI production check supplies both options to test that configuration; it does not establish that an actual hosting domain is suitable.

## Reporting

For a public repository, use GitHub's private vulnerability-reporting feature if the maintainer has enabled it. Otherwise contact the repository owner privately. Do not post credentials or student records in a public issue.

Relevant primary guidance: [Django deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/), [Django security releases](https://www.djangoproject.com/weblog/2026/aug/04/security-releases/), [Gemini key management](https://ai.google.dev/gemini-api/docs/api-key), [GitHub secret scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning).
