# Documentation Index

This directory keeps the documents that still match the current repository state.

## Active Documents

- `architecture-review-and-plan.md`
  Architecture review of the current backend, frontend, and engineering boundaries.
- `refactor-task-roadmap.md`
  Executable refactor backlog derived from the architecture review.
- `ui-ux-multilayer-redesign.md`
  Current frontend multilayer workspace model and implemented redesign notes.
- `sqlite-output-resume-upgrade-plan.md`
  Design plan for optional SQLite output, durable sinks, and checkpoint-based resume.
- `script-first-production-crawler-plan.md`
  Revised plan for delivering SQLite/resume through multi-stage script generation, rewrite, and evaluation.
- `workflows/eworldship_product_1772.json`
  Example workflow DSL for the `eworldship` collection scenario.

## Source-Of-Truth Documents Outside `docs/`

- `README.md`
  Project overview, startup commands, and high-level structure.
- `DESIGN.md`
  Current design system and frontend implementation guidance.
- `AGENTS.md`
  Repository-level development rules and contributor guidance.

## Removed / Consolidated

- `PLAN.md`
  Historical feature planning for an earlier product shape. It no longer matches the current React workbench and API structure.
- `frontend-redesign-roadmap.md`
  Superseded by `DESIGN.md` plus `ui-ux-multilayer-redesign.md`.

## Cleanup Rule

Keep a document only if it does at least one of the following:

- describes the current codebase accurately
- serves as the source of truth for an actively maintained subsystem
- contains an example workflow still reused during development

If a file is only a phase artifact, temporary investigation note, or already absorbed by a newer document, delete it instead of archiving duplicate guidance.
