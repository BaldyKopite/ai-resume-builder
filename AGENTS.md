# Superpowers Agent Guidelines

This repository follows the Superpowers engineering methodology:

## 1. Initial Step: Skill Invocation & Methodology (`using-superpowers`)
- **Always invoke skills before action:** Check and activate the appropriate Superpowers skill before executing tasks, writing code, or proposing solutions.
  - **New Features / Architecture:** Use `brainstorming` before entering planning or implementation.
  - **Debugging / Issues:** Use `systematic-debugging` to trace and reproduce root causes before modifying files.
  - **Implementation:** Use `test-driven-development` (write failing tests before implementation code).
  - **Complex Tasks:** Use `writing-plans` and `subagent-driven-development`.
- **Task Tracking:** For multi-step tasks, create and maintain an explicit task checklist, updating progress systematically.

## 2. Final Step: Verification Before Completion (`verification-before-completion`)
- **Strict Evidence Requirement:** NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.
- Before claiming work is finished, resolved, or passing:
  1. Determine the exact command or test that proves the change works.
  2. Run the full command fresh and inspect the output and exit status.
  3. Confirm the output verifies the claim with tangible evidence.
  4. Only after providing the evidence, mark the task as complete.
