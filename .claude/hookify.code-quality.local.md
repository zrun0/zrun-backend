---
name: warn-debug-artifacts
enabled: true
event: file
action: warn
pattern: \bprint\(|breakpoint\(\)|import\s+pdb|pdb\.set_trace\(\)|\.set_trace\(\)
---

⚠️ **Debug artifact detected**

A debug statement was added to the file:
- `print(...)` — use `structlog` (project standard) instead
- `breakpoint()` — remove before committing
- `pdb` / `set_trace()` — remove before committing

These should not be committed to the repository. Use structlog for all logging in this project.
