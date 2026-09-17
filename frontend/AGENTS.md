# SeekHarness — Frontend Policy (`frontend/`)

> Scoped instructions for Vite + React + TypeScript web client.
> Inherits the canonical engineering mission and product invariants from
> [`../AGENTS.md`](../AGENTS.md). These are component policies, not agent ownership
> restrictions: either AG or Codex may implement work here for an assigned task.

---

## 1. Observer / Controller Role

- **No Client-Side State Ownership**: The frontend is strictly an observer and dispatching controller. It never authors, mutates, or finalizes official Battle state, scores, or rankings.
- **Backend Provenance Required**: Every `VERIFIED`, `RANKED`, or `COMPLETED` badge or label must originate from verified backend data fields with verifiable provenance.
- **Honest Lifecycle States**: Optimistic UI transitions must be labeled as pending/in-flight and never presented as authoritative or terminal until confirmed by the backend via SSE or REST response.

---

## 2. Integrity of Display & Telemetry

- **No Synthetic Activity**: Never inject fake terminal events, dummy token counters, or simulated progress animations to make an idle or pending battle appear actively running.
- **No Mock / Demo Telemetry as Real**: Real battle views must stream authentic SSE telemetry. Mock or demonstration data must be explicitly demarcated as synthetic.
- **No Inferred Win/Loss**: Never calculate, extrapolate, or display Win/Loss records or winner banners solely from Elo differentials or rating shifts. Win/Loss belongs exclusively to the Arena-authoritative backend result.
- **No Fabricated Skill Badges**: Do not derive or render competency badges (e.g., "SQL Injection Specialist", "Fast Patcher") from model marketing names or arbitrary heuristics. Badges must reflect measurable backend benchmark results.
- **Canonical Model Provenance**: Display provider and model identities using canonical backend provenance fields, avoiding client-side hardcoded aliases or misattributed provider labels.

---

## 3. Target, Format & Error Truthfulness

- **Contract-Driven UI**: Target specifications, parameters, and Execution Format rules must be driven by resolved backend API contracts (`/formats`, `/targets`), never by hardcoded client fallbacks, client assumptions, or arbitrary array indices.
- **Honest Failure Surfacing**: Surface backend errors, infrastructure timeouts, and provider rate limits (429/502/OOM) with accurate diagnostics rather than masking them as generic match cancellations or fighter concessions.
- **Unambiguous Unknown States**: When telemetry, provenance, or verification status is unavailable, render honest `Unknown`, `Unverified`, or `Unranked` states rather than defaulting to affirmative claims.
