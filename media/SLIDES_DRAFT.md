# DISTORTED REALITY
## Sandboxed AI Workflow Execution with Cryptographic Evidence on Vultr
### Vultr Agent Rush Hackathon · November 2026

---

## Slide 1: Executive Overview
- **Product**: Distorted Reality
- **Submission Track**: Blast Radius Zero (Pattern A: Sandboxed Code Execution)
- **Product Surface**: Powering the Future of Work (Accounts Payable Team Workflow)
- **Core Differentiator**: The Proof Layer
  - AI agents routinely claim completion without checkable evidence.
  - Distorted Reality isolates untrusted execution in throwaway sandboxes and recomputes all metrics in the control plane.
- **License**: MIT License · Copyright (c) 2026 Larry D. Ross

---

## Slide 2: The Core Problem in Agentic Workflows
- **The "Done" Illusion**:
  - LLM agents frequently emit `"status": "completed"` while skipping critical verification steps.
  - In financial workflows (such as AP 3-way matching), an unverified completion claim results in payment of invalid or fraudulent invoices.
- **Why Output Checking Fails**:
  - Validating JSON schemas only checks format, not truth.
  - Self-reported agent telemetry cannot be trusted to self-audit.
- **The Distorted Reality Solution**:
  - **Deterministic MRI**: Scans existing handoffs read-only before any model runs.
  - **Multi-Model Council**: Explores diverse workflow paths under blinded neutral labels.
  - **Container Sandbox Isolation**: Executes generated code with zero network access and strict resource caps.
  - **Control-Plane Recomputation**: Every claim is checked against raw evidence; discrepancies are surfaced, not hidden.

---

## Slide 3: Two-Tier Architecture (T1 Topology)
```
Browser ──HTTPS──▶ [CONTROL VM C] Caddy (Reverse Proxy) + App
                     • Orchestrator & State Machine
                     • Inference Broker (Holds ONLY Vultr Key)
                     • Digital MRI & G5 Scorer
                     • Claim-vs-Evidence Checker & Metrics Recompute
                     • Hash-Chained Append-Only Journal
                     • Heartbeat Endpoint /healthz (Polled 100ms)
                         │
                         │ Docker over SSH (DOCKER_HOST=ssh://runner@S)
                         ▼
                   [SANDBOX HOST S] (Secret-Free, No Outbound Internet)
                     └─ Single Container per Run:
                        • Flag: --network none (Zero Network Access)
                        • Flag: --read-only rootfs + 32MB tmpfs
                        • Flag: --cap-drop ALL --security-opt no-new-privileges
                        • Hard Caps: 256MB RAM, 1 CPU, 64 PIDs, 30s Wall-Clock
                        • Standard I/O: Stdin JSON In ➔ Stdout JSON Out
                        • Destroy Verified: Container removed after attempt
```

---

## Slide 4: Deterministic Digital MRI & G5 Assessment
- **Digital MRI**:
  - Deterministic Python scanner audits the 7-step AP workflow (PO placed, Delivery counted, Log receipt, Invoice received, 3-way match, Exception review, Payment recommendation).
  - Stamped read-only inventory mapping role handoffs, wait times, and stall points.
  - Authorizes nothing and invokes zero LLMs.
- **G5 Assessment & Public Suppression**:
  - 15 operational questions evaluated on a 1–6 scale.
  - Public result emits **Overall Index (17–100)** and **Generic Recommendation** only.
  - Full suppression of internal system scores and question-keyed answer vectors.
  - Mandatory disclosure notice rendered on all surfaces.

---

## Slide 5: The Third Path Council (Vultr Inference)
- **All agent LLM calls route through Vultr Serverless Inference (`api.vultrinference.com/v1`)**:
  - **Evidence Agent** (`mimo-v2.6-flash`): Extracts operational facts and constraints.
  - **Path Agent** (`glm-5.3`): Formulates three distinct interventions with varied check orders and automation.
  - **Critic Agent** (`deepseek-v4.1-flash-1017`): Challenges hidden bottlenecks, strawman arguments, and overlaps.
  - **Decision Agent** (`mimo-v2.6-pro`): Evaluates paths on blinded neutral labels (`option-1..3`), reducing presentation framing bias.
- **Fail-Closed Inference Broker**:
  - Validates `response.model` against requested model id on every single call.
  - Enforces per-run and daily token budgets to limit spend and prevent runaway consumption.

---

## Slide 6: The Proof Layer: Claim Check & Metrics Recompute
- **Claim-vs-Evidence Engine**:
  - For every assertion `{case_id, step_id, claimed, evidence_ref}`:
  - Resolves `evidence_ref` against raw event logs.
  - Classifies each claim as `SUPPORTED`, `UNSUPPORTED`, or `CONTRADICTED`.
  - A path with even a single unsupported claim receives a verdict of `CLAIMS_FAIL` and is ineligible to win.
- **Eligibility & Pre-Registered Decision Rule**:
  - **Eligibility Criteria**: Clean claim check (`CLAIMS_PASS`), zero unsupported claims, false alarms at most a configured fraction of cases.
  - **Decision Rule** (`dr-3way-v1`): Hashed and journaled before sandbox execution.
  - **Ranking Metrics**: Among eligible candidates, ranked by verified exceptions caught (higher is better) and manual touches (lower is better).
  - **Threshold Margin**: Minimum margin (>= 3 verified exceptions caught over next candidate).
  - No forced winners: `NO_SUFFICIENT_EVIDENCE` is a valid, first-class outcome.

---

## Slide 7: Technical Containment & Runaway Termination
- **Blast Radius Zero Architecture & Technical Controls**:
  - Untrusted model code runs with `--network none` (container network access disabled, no outbound traffic).
  - Host filesystem is untouched; non-root user `65534:65534` with all Linux capabilities dropped.
- **Canary Secret Hygiene Test**:
  - Control VM env sets canary secrets; sandbox dump proves canary is completely absent.
  - Paired negative control: intentionally seeded canary fails test, verifying detector sensitivity.
- **Watchdog Protection**:
  - Three-tier termination: In-harness soft alarm, Controller `docker kill`, and independent systemd reaper timer.
  - Runaway stress workload killed cleanly by cgroup at 256 MB cap with zero control-plane heartbeat disruption.

---

## Slide 8: Human Approval Gate & Offline Verification
- **Human Approval Gate**:
  - Reviewer inspects the complete evidence packet and confirms review.
  - `external_action_taken: false` is a permanent schema constant: approval authorizes zero payments or external mutations.
- **Independent Offline Verification**:
  - Generates unguessable verification bundle: `packet.json`, `journal.jsonl`, `events.json`, `decision_rule.yaml`.
  - Standalone verification script (`tools/verify_packet.py <bundle_dir>`) independently recomputes hash chains, validates schema integrity, and detects any journal tampering without internet access.

---

## Slide 9: Project Lineage & Compliance
- **Synthetic Data Notice**:
  - Built against synthetic AP dataset (Ember & Oak Hospitality Group, 200 cases, seed 20261103).
  - All metrics certify calculations under stated assumptions only; no real-world business improvement is claimed.
- **Originality & AI Disclosure**:
  - Written new for the Vultr Agent Rush Hackathon (Nov 3–8, 2026) under the originality conditions specified in REUSE_AUDIT.
  - Created with autonomous AI coding agents under human instruction and supervision; no prior private source files incorporated.
  - Open Source: MIT License · Copyright (c) 2026 Larry D. Ross.
