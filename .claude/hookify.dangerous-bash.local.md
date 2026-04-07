---
name: warn-dangerous-bash
enabled: true
event: bash
action: warn
pattern: rm\s+-rf|chmod\s+777|git\s+push\s+--force|--no-verify|dd\s+if=
---

> 🚨 **DANGEROUS COMMAND DETECTED** 🚨
>
> **This command matches a DESTRUCTIVE pattern:**
>
> - `rm -rf` — recursive force delete
> - `chmod 777` — insecure permissions
> - `git push --force` — **overwrites remote history**
> - `--no-verify` — **skips git hooks/safety checks**
> - `dd if=` — raw disk operation
>
> **STOP and verify the target path/flag is correct before proceeding!**
