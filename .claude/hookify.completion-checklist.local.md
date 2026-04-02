---
name: completion-checklist
enabled: true
event: stop
action: warn
pattern: .*
---

📋 **Before stopping, verify:**

- [ ] Ran `just check` (format + lint + typecheck)?
- [ ] Ran `just test <service>` for affected services?
- [ ] No debug artifacts left (`print()`, `breakpoint()`, `pdb`)?
- [ ] All TODO items in this task addressed?
- [ ] Proto changes compiled with `just proto` if `.proto` files were modified?

If any item is incomplete, continue working before stopping.
