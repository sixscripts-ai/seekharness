# Vertical Slice Disciplines & Evidence Ladder Reference

## 1. The 4-Tier Evidence Ladder

When building or updating features across the SeekHarness battle lifecycle, work must progress sequentially through four distinct evidence tiers:

1. **`Tier 1: IMPLEMENTED`**
   - Core domain logic, schemas, and models exist.
   - Syntax is valid, and static imports resolve.
   - Unit tests pass in complete isolation without external dependencies.

2. **`Tier 2: WIRED`**
   - The module is connected to application entrypoints (routers, event bus, database models).
   - Component contracts match across callers and callees.
   - Config flags or environment variables are properly wired and defaulted.

3. **`Tier 3: TESTED`**
   - Automated boundary and integration tests pass.
   - Negative tests verify expected failure modes (malformed inputs, timeouts, disconnections).
   - Invariant checks confirm state machines cannot reach corrupted states.

4. **`Tier 4: LIVE_OBSERVED`**
   - The boundary executes cleanly in an end-to-end evaluation run.
   - Telemetry logs prove correct transition timing and error handling.
   - Finalization and teardown leave zero leaked resources.

## 2. Single Vertical Slice Principle

- **Do NOT build horizontally across multiple unverified features.**
- Complete one vertical slice across backend, contracts, and tests before starting another.
- If an existing slice is broken, regression must be stopped and the slice repaired before new functionality is introduced.
