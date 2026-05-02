# Change Control

## Phase 1 no-write policy
Phase 1 is strictly read-only.

The agent must not:
- insert data
- update data
- delete data
- create or alter schema
- auto-fix findings

## Phase 2 approval workflow
The only allowed write-capable workflow in phase 2 is:
- approved spelling lesson-name correction
- app = `spelling`
- table = `public.spelling_words`
- course_id = `9`

Every approved write must require:
- approver ID
- timestamp
- before value
- proposed after value
- rollback plan
- bounded batch size

## Required approver metadata
- human approver ID
- reason for change
- scope of records
- run ID that produced the recommendation

## Rollback requirement
No mutation should occur without a documented rollback path.

## Batch approval limit
Future write batches should be intentionally small and reviewable. Bulk unbounded approval is not acceptable.

## Audit trail requirement
Every approved change must have:
- who approved it
- when
- what changed
- why
- what the rollback path is
