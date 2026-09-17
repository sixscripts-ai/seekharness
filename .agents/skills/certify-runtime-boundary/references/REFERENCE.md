# Runtime Boundary Certification Reference

## 1. Boundary Certification Criteria

A runtime boundary is declared **CERTIFIED** if and only if all of the following conditions are met:

1. **Deterministic Test Execution**: All focused boundary test files exist and pass with exit code `0`.
2. **Negative Invariant Validation**: Negative tests explicitly verify that illegal states, malformed commands, and out-of-boundary tool calls are rejected safely.
3. **No Unmanaged Side Effects**: Execution does not leak file descriptors, orphan background subprocesses, or leave ephemeral database branches uncleaned.
4. **Zero Flakiness**: The boundary test suite executes repeatably within deterministic timeout limits (<5 seconds for unit suites).

## 2. Invariant Rules by Boundary

- **`semantic_verification`**: Verifier must reject unauthorized command injection attempts and enforce strictly AST-verified tool boundaries.
- **`battle_db`**: Ephemeral Neon branch handles must be isolated per battle ID; tear-down hooks must release all allocated resources.
- **`service_lifecycle`**: Reaper must terminate hung worker processes and release allocated ports upon battle timeout or abnormal termination.
- **`breaker_handoff`**: Fighter network policies must enforce egress firewalls; frozen artifacts cannot be mutated after handoff.
- **`trusted_completion`**: Transactional finalization must produce tamper-evident audit logs and prevent double-spending or score modification.
