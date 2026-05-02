# Kiarolabs Content Quality Agent

`kiarolabs-content-quality-agent` is an offline content audit agent for Kiarolabs learning content.

## What it does
- audits Words content quality for synonym, antonym, compound-word, and headword-answer mapping issues
- audits Spelling content quality for pattern assignment, hint relevance, example relevance, and lesson outliers
- generates Markdown, JSON, CSV, coverage, schema-discovery, and diff reports
- supports deterministic checks with optional LLM-assisted semantic review
- detects canonical spelling pattern lessons for course `9`
- generates approval templates for spelling lesson corrections

## What it does not do
- it does not mutate production data
- it does not insert, update, delete, or migrate schema
- it is not a runtime app
- it is not part of `kiarolabs-membership-service`
- it does not auto-fix anything in phase 1
- it does not apply any production change without an explicitly approved CSV in phase 2

## Phase 1 read-only guarantee
Every query passes through `GuardrailEnforcer`, which blocks:
- non-SELECT SQL
- write keywords
- unknown tables
- cross-app reads

If schema discovery is uncertain, the agent stops that audit group and reports the failure instead of guessing.

## Configuration
Environment variables:
- `CONTENT_AUDIT_DB_URL`
- `OPENAI_API_KEY` (optional)
- `CONTENT_AUDIT_REPORTS_DIR`
- `CONTENT_AUDIT_FAIL_ON`

See [CONFIGURATION.md](/C:/Users/DND/Documents/Codex/2026-04-18-github-plugin-github-openai-curated-can/kiarolabs-content-quality-agent/CONFIGURATION.md).

## How to run

### Dry-run
```bash
python main.py --mode all --dry-run
```

### Words audit
```bash
python main.py --mode words --limit 100
```

### Spelling audit
```bash
python main.py --mode spelling --lesson-id 870
```

### Full audit
```bash
python main.py --mode all --reports-dir reports
```

### Generate spelling fix suggestions
```bash
python main.py --mode generate-fixes --source reports/content-quality-errors.csv
```

### Validate approved spelling fixes without writing
```bash
python main.py --mode apply-approved-fixes --file approved_fixes.csv --dry-run
```

### Apply approved spelling fixes
```bash
python main.py --mode apply-approved-fixes --file approved_fixes.csv
```

## Reports
Each run writes:
- `reports/runs/<run_id>/content-quality-report.md`
- `reports/runs/<run_id>/content-quality-report.json`
- `reports/runs/<run_id>/content-quality-errors.csv`
- `reports/runs/<run_id>/coverage.json`

Latest pointers:
- `reports/content-quality-latest.md`
- `reports/content-quality-latest.json`
- `reports/content-quality-errors.csv`
- `reports/content-quality-coverage-latest.json`
- `reports/audit-diff-latest.md`
- `reports/audit-diff-latest.json`

## Confidence
- `>= 0.95`: strong recommendation, still human-reviewed
- `0.80 - 0.94`: human review required
- `0.60 - 0.79`: informational / weak signal
- `< 0.60`: no finding unless a critical deterministic rule fails

## Coverage
A clean report is only trustworthy when coverage is high. If semantic checks are skipped because `OPENAI_API_KEY` is missing, the run should be treated as partial.

## Limitations
- words schema discovery is intentionally conservative
- some semantic checks degrade or skip without an LLM key
- phase 1 reports recommendations only; it never applies them
- phase 2 only supports approved spelling lesson-name corrections on `course_id = 9`
