# Superpowers Project Rules

Always enforce Superpowers as the first and last step of every conversation and task:

1. **First Step (Conversation Start):**
   - Check if any skill in `superpowers` applies.
   - Invoke `using-superpowers` before any response or action (including clarifying questions or exploring the codebase).
   - If planning or designing: Invoke `brainstorming` first, then `writing-plans`.
   - If fixing a bug: Invoke `systematic-debugging`.
   - If writing code: Use `test-driven-development` and `subagent-driven-development`.

2. **Final Step (Completion Verification):**
   - Before declaring any task finished or complete, invoke `verification-before-completion` to thoroughly verify all requirements against tests and evidence.
