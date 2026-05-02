# content-quality-guardrails

Phase 1 is read-only.

Guardrails must block:
- INSERT
- UPDATE
- DELETE
- ALTER
- CREATE
- DROP
- TRUNCATE
- unknown tables
- cross-app reads

No silent schema guessing is allowed.
