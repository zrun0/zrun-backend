---
name: warn-sensitive-files
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.env$|\.env\.|credentials|secrets?\.ya?ml$|\.pem$|\.key$
---

⚠️ **Sensitive file edit detected**

You are editing a file that may contain secrets or credentials.

Before proceeding:
- Confirm this file is listed in `.gitignore`
- Do not hardcode plaintext secrets — use environment variable references
- Avoid committing API keys, passwords, or private keys

If this is intentional (e.g. updating a `.env.example`), proceed carefully.
