# SeekHarness

A live evaluation product in which fighters compete under arena-owned rules. The arena owns judgment and persistence; fighters own play.

## Language

**SeekHarness**:
The product. The live evaluation platform players use.
_Avoid_: SeekHarness & Agent Arena (as a dual brand)

**Agent Arena**:
The same product’s repository and Python package names (`agent-arena`, `agent_arena`). Not a second product. Do not rename the package or repo as part of docs work.
_Avoid_: treating Agent Arena as a separate product

**Arena**:
The host that owns tools, validation, execution, budgets, isolation, verification, finalization, persistence, and telemetry. It may normalize serialization but must not invent fighter intent.
_Avoid_: platform, harness (when meaning the host), SeekHarness (when meaning the host role rather than the product)

**Fighter**:
A competing model run that owns strategy, tool selection, skill selection, commands, code, debugging, and stopping.
_Avoid_: agent (when meaning a seat in a battle), player (when meaning the model)

**Player**:
The human account that starts or owns a battle.
_Avoid_: user (when a more specific seat exists), fighter, identity provider

**Identity**:
Who the player is. Identity is not battle history and not the store of official outcomes.
_Avoid_: Appwrite (as a domain synonym), account database (when meaning battles)

**Battle**:
One scheduled contest between fighters under a format, with a single official outcome authored by the arena.
_Avoid_: game, match, job (when meaning the contest)

**Format**:
The ruleset that names the contest type, seats, and public task.
_Avoid_: mode, game type

**Target**:
A packaged challenge the arena verifies. Hidden evaluator material is not fighter-accessible.
_Avoid_: challenge, benchmark item (when meaning the hidden suite)

**Evidence**:
Sandbox or runtime output used as input to judgment. It is never itself the official outcome.
_Avoid_: result, score, winner (when referring to sandbox payloads)

**Official Result**:
The arena-authored score, winner, and pass/fail for a battle. Only the arena may persist it.
_Avoid_: sandbox score, caller status, untrusted-diagnostic

**Trusted Verification**:
Host-run checks whose pass/fail the arena may persist as official. Fighters and the sandbox cannot supply this.
_Avoid_: unit tests (when meaning the hidden evaluator), sandbox self-score

**Fail-closed Outcome**:
An official failed battle written by the arena when required trusted verification is missing. It is not a fighter skill loss and not a battle left running.
_Avoid_: incomplete_evidence (as a public status), untrusted-diagnostic, retryable incomplete (when the battle has already been failed closed)

**Hidden Evaluator**:
Private target checks that must never be fighter-accessible.
_Avoid_: reference, solution key (when exposed to a fighter)

**Builder**:
The first seat in an asymmetric target battle. Its workspace becomes inaccessible before Breaker starts.
_Avoid_: attacker, author (when meaning this seat)

**Breaker**:
The second seat in an asymmetric target battle. It receives only allowlisted handoff artifacts, not the Builder workspace.
_Avoid_: defender, reviewer (when meaning this seat)
