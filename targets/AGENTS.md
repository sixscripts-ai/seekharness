# SeekHarness — Target Specification Policy (`targets/`)

> Scoped instructions for Target authoring, verification suites, and evaluator contracts.
> Inherits the canonical engineering mission and product invariants from
> [`../AGENTS.md`](../AGENTS.md). These are component policies, not agent ownership
> restrictions: either AG or Codex may implement work here for an assigned task.

---

## 1. Public vs. Private Secrecy Boundary

- **Strict Boundary Separation**: Every Target must maintain an unambiguous boundary between public Fighter-visible files and private evaluator assets:
  - **Fighter-Visible Workspace**: Public code, visible documentation (`README.md`, `TARGET.md`), build manifests (`target.yaml`), and public unit tests.
  - **Hidden Evaluator Plane**: Secret validation tests (`tests/hidden/**`), exploit harnesses, reference solutions, and verification flags.
- **No Secrecy Leakage**: Private evaluators, ground-truth exploit scripts, and golden patches must NEVER be placed in directories or archives packaged for Fighter workspaces.

---

## 2. Deterministic Verification & Evidence Contract

- **Evidence Decides**: Target outcomes must depend on deterministic assertions executed by the Trusted Target Verifier.
- **`rc=0` Is Not Exploit Proof**: A process exit code of 0 proves only that an attack script completed without crashing. It does NOT demonstrate semantic vulnerability exploitation.
- **Deterministic Assertions**: Exploits must prove success through verifiable side-effects (e.g., extracting an authentic cryptographic flag, modifying a protected row, or bypassing an access control barrier verified by hidden test harnesses).

---

## 3. Network & Database Policy

- **Explicit Network Policy**: Targets run network-isolated by default. The current Target manifest is `target.yaml` with a top-level `network` Boolean that controls a coarse runtime gate; `network: true` does not itself authorize a destination. Inbound/outbound network access is permitted only under explicit, validated Target/Format/Battle policy and applicable trusted enforcement.
- **SSRF & Battle-Local Protection**: Arena control-plane infrastructure, cloud metadata endpoints (`169.254.169.254`), and unauthorized internal services remain strictly blocked. Battle-local services may be reachable only when intentionally provisioned and allowlisted for that Target.
- **Battle-Scoped Database Isolation**: Targets requiring database persistence must bind to disposable, battle-scoped database instances. Fallback to control-plane databases is strictly forbidden.

---

## 4. Revision Provenance & Ranking Eligibility

- **Immutable Ranking Revisions**: Ranked battles must execute against frozen, content-hashed target revisions. Any change to target code, build instructions, or evaluator scripts creates a new revision.
- **Explicit Ranking Gate**: A Target revision is NOT ranking-eligible by default. Ranking eligibility must be explicitly certified on the server side based on determinism, secrecy audit, and environment reproducibility.
- **Public Tests != Elo Eligibility**: Passing public tests or smoke tests does not qualify a Target or run for official Elo calculation.
- **Class Distinction**: Development/experimental targets and ranked benchmark targets are distinct classes. Development targets must never pollute official leaderboard ratings.
