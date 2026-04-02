---
name: warn-dangerous-bash
enabled: true
event: bash
action: warn
pattern: rm\s+-rf|chmod\s+777|git\s+push\s+--force|--no-verify|dd\s+if=
---

⚠️ **Dangerous command detected**

This command matches a potentially destructive pattern:
- `rm -rf` — recursive force delete
- `chmod 777` — insecure permissions
- `git push --force` — overwrites remote history
- `--no-verify` — skips git hooks/safety checks
- `dd if=` — raw disk operation

Please verify the target path or flag is correct before proceeding.
