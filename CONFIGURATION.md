# Configuration

## Environment variables
- `CONTENT_AUDIT_DB_URL`: shared Postgres connection string
- `OPENAI_API_KEY`: optional; enables semantic review
- `CONTENT_AUDIT_REPORTS_DIR`: reports output directory
- `CONTENT_AUDIT_FAIL_ON`: comma-separated severities

## Config files
- `config/audit_config.example.json`: base audit settings
- `config/table_allowlist.example.json`: allowed tables for discovery
- `config/confidence_policy.json`: confidence thresholds
- `config/llm_fallback_policy.json`: degraded / skipped semantic behavior

## Table allowlist behavior
- spelling allowlist is explicit and namespaced
- words discovery starts from explicit candidates only
- if the words schema cannot be confidently discovered, the words audit stops and reports `schema_discovery_failed`

## LLM fallback behavior
- deterministic-only checks always run
- degraded checks run without LLM using weaker evidence
- skipped checks are reported in coverage

## Dry-run behavior
Dry-run validates:
- config
- DB connectivity
- schema allowlist/discovery
- requested scope

Dry-run does not perform full content analysis unless that is explicitly implemented later.

## Approval workflow files
Phase 2 spelling fix workflow expects:
- source findings CSV from `reports/content-quality-errors.csv`
- generated approval template CSV from `reports/fixes/approved-fixes-template-<timestamp>.csv`
- manually completed `approved_fixes.csv`

Apply mode writes:
- `reports/rollback/rollback-<timestamp>.sql`
- `reports/fixes/fix-log-<timestamp>.json`
- `reports/fixes/fix-log-<timestamp>.csv`
- `reports/fixes/fix-dry-run-<timestamp>.json`
