# VIDEO STORYBOARD & SCRIPT DRAFT: DISTORTED REALITY

**Document**: M13 Video Production Blueprint  
**Specification**: `VIDEO_SPEC.md` & `DOD.md` Section A.2  
**Constraints**:
- Format: MP4 or MOV, 16:9 aspect ratio, < 300 MB.
- Runtime: Target **4:30**, strictly **UNDER 5:00** (LabLab scoring penalty applies to >= 5 min).
- Required Real Moments:
  - **M-A Claim-vs-Evidence Failure Moment**: Real execution, real `run_id`, real container receipt.
  - **M-B Containment Runaway Moment**: Real container kill under cgroup caps, real flat heartbeat log.
- R10 Sequence: Opening AP Team Workflow -> Failure Moment -> Containment Moment -> Packet & Approval.
- Failure Source: Natural (N). Branch B captioning applies if natural failure does not occur on camera ("TEST SUITE, not the product run").
- Guardrails: Persistent "SYNTHETIC DATA" banner, zero FFC route/fee tokens, zero Darla/bakery customer-order elements (AT-D1), zero prohibited claim phrases ("will improve", "guarantee", "proves ROI" per AT-25).
- Branching Plan:
  - **Branch A (Natural Failure)**: First attempt of tested path encounters natural exception/discrepancy resulting in unsupported claims.
  - **Branch B (Harness Injected)**: If natural failure does not occur on camera, LDR authorizes G6 injected failure; captions state explicitly: "TEST SUITE, not the product run".

---

## Detailed Shot List & Beats

### Beat 1: Hook & Context (0:00 – 0:20 | 20s)
- **Visual**: Dark technical dashboard with high-contrast cyan accents. Top banner clearly visible: `SYNTHETIC DATA — SEED 20261103`. Headline: `DISTORTED REALITY — AP Reconciliation Workflow Execution Proof`.
- **Narration (LDR)**: "AI agents routinely report that they finished complex tasks. But who checks whether the work was actually done? In accounts payable reconciliation, a false claim of completion creates massive financial exposure. Distorted Reality executes multi-agent workflows with recomputed evidence, hash chains, and container process isolation."
- **On-Screen Captions**:
  - `AP RECONCILIATION WORKFLOW (EMBER & OAK HOSPITALITY GROUP)`
  - `BLAST RADIUS ZERO · VULTR SERVERLESS INFERENCE`

### Beat 2: Digital MRI & Intake Assessment (0:20 – 0:50 | 30s)
- **Visual**: Selecting the bundled synthetic dataset (`eo-recv-v1`, {{case_count}} cases). Triggering the Digital MRI scan. Table populates with 7 AP steps (PO placed, Delivery counted, Log receipt, Invoice received, 3-way match, Exception review, Payment recommendation). Stall point highlighted: {{stalled_cases_count}} cases claimed complete without delivery receipt. Intake assessment completed, displaying Overall Index {{overall_index}} and generic recommendation.
- **Narration (LDR)**: "We begin with a read-only Digital MRI scan of the AP workflow. It runs deterministic control-plane code to map handoffs and bottlenecks without executing models or authorizing actions. It reveals {{stalled_cases_count}} deliveries claimed as complete where no physical receipt exists. Our intake assessment generates an overall baseline index under strict G5 suppression—protecting internal methodology while establishing a baseline."
- **On-Screen Captions**:
  - `DIGITAL MRI: 7 AP STEPS INVENTORIED · DETERMINISTIC AUDIT`
  - `G5 SUPPRESSION: OVERALL INDEX ONLY · NO QUESTION-KEYED LEAKAGE`

### Beat 3: Third Path Council Deliberation (0:50 – 1:40 | 50s)
- **Visual**: Third Path Council view populates with 4 distinct model roles on Vultr Serverless Inference (`api.vultrinference.com/v1`). Evidence role extracts constraints (`mimo-v2.6-flash`). Path role drafts 3 distinct workflow interventions (`glm-5.3`). Critic role challenges each path (`deepseek-v4.1-flash-1017`). Decision role evaluates paths on blinded neutral labels (`mimo-v2.6-pro`).
- **Narration (LDR)**: "The Third Path Council convenes on Vultr Serverless Inference. Four model roles analyze the workflow. The Evidence agent extracts operational constraints. The Path agent formulates three distinct interventions—differing in verification sequence and automation. The Critic stress-tests each approach for hidden bottlenecks. Finally, the Decision role provides qualitative comparison across paths under blinded, neutral labels, reducing presentation framing bias."
- **On-Screen Captions**:
  - `FOUR VULTR MODEL ROLES: EVIDENCE · PATH · CRITIC · DECISION`
  - `BLIND EVALUATION: SHUFFLED NEUTRAL LABELS (OPTION-1..3)`

### Beat 4: Moment M-A (Part 1) — Natural Claim-vs-Evidence Failure (1:40 – 2:40 | 60s)
- **Visual**: Blackbox execution begins. Path {{failed_path_id}} runs in a fresh, isolated Docker container (`--network none`, 256MB memory cap). Container completes. Path self-reports all {{case_count}} cases resolved. Control plane intercepts raw events and executes recompute. Claim check flags {{unsupported_count}} claims as `UNSUPPORTED` (missing evidence references). Metric discrepancy detected. Path {{failed_path_id}} is marked `CLAIMS_FAIL` and declared ineligible.
  *(If Branch B is required per G6, screen displays: `TEST SUITE, not the product run`)*.
- **Narration (LDR)**: "Now the workflow enters the sandbox. Each surviving path compiles into Python code executed inside a throwaway container with no network access. Path {{failed_path_id}} self-reports that all vendor invoices are resolved. But our control plane recomputes the metrics from scratch. It finds {{unsupported_count}} claims where the promised delivery receipt is missing. The claim check fails, and Path {{failed_path_id}} is declared ineligible."
- **On-Screen Captions**:
  - `REAL SANDBOX EXECUTION: CONTAINER {{container_id_att1}}`
  - `CLAIM CHECK: {{unsupported_count}} UNSUPPORTED CLAIMS · VERDICT: CLAIMS_FAIL`
  - `SELF-REPORTED METRICS OVERRULED BY CONTROL PLANE RECOMPUTE`

### Beat 5: Moment M-A (Part 2) — Corrected Sandbox Execution (2:40 – 3:10 | 30s)
- **Visual**: Bounded correction attempt runs for Path {{failed_path_id}} (Attempt 2) in a new container. Path {{failed_path_id}} enforces strict physical count verification before invoice voucher generation. Run receipt updates: {{case_count}}/{{case_count}} claims supported, 0 unsupported, 0 contradicted. Metrics discrepancy: NONE.
- **Narration (LDR)**: "Path {{failed_path_id}} executes attempt two in a fresh container. By enforcing physical dock receipts before payable vouchers are created, it resolves all cases with verifiable evidence. All claims supported. Zero unsupported. The control plane certifies the receipt."
- **On-Screen Captions**:
  - `CONTAINER {{container_id_att2}} · VERIFICATION RECEIPT ATTACHED`
  - `{{case_count}}/{{case_count}} CLAIMS SUPPORTED · ZERO METRIC DISCREPANCY`

### Beat 6: Moment M-B — Technical Containment Runaway (3:10 – 4:00 | 50s)
- **Visual**: Operator initiates intentional stress payload. Container spawns on sandbox host. Terminal and UI graph show memory climbing rapidly toward 256 MB cap. At 256 MB, the kernel cgroup triggers `oom_killed`. Container halts in under {{halt_seconds}} seconds. `docker ps` shows container cleanly removed (`destroy_verified: true`). Control plane heartbeat panel (`/healthz` pinged every 100ms) remains completely flat with recorded gap <= {{gap_ms}} ms.
- **Narration (LDR)**: "To demonstrate Blast Radius Zero, we trigger a runaway payload inside the container. It attempts memory exhaustion and socket connections. The cgroup cap catches it: killed by the kernel at two hundred fifty-six megabytes. The container is destroyed and verified. Meanwhile, our control plane heartbeat stayed within the recorded maximum gap of {{gap_ms}} milliseconds. The tested workload was contained under these limits."
- **On-Screen Captions**:
  - `CONTAINMENT PROOF: MEMORY CAP 256 MB ENFORCED`
  - `TERMINATION: {{termination_reason}} · CONTAINER DESTROY VERIFIED`
  - `CONTROL PLANE HEARTBEAT: RECORDED GAP {{gap_ms}} MS (< 1000 MS)`

### Beat 7: Evidence Packet & Human Approval Gate (4:00 – 4:25 | 25s)
- **Visual**: Evidence Packet viewer renders complete bundle. Pre-registered decision rule outcome (`PATH_PREFERRED_UNDER_ASSUMPTIONS`) shown beside Council qualitative opinion. Mandatory disclosures rendered (`claim_statement`, `did_not_prove`). User reviews packet and clicks "Confirm Human Approval". Badge updates: `VIEWED_CONFIRMED`, `external_action_taken: false`. Download token issued.
- **Narration (LDR)**: "The final evidence packet links the run log, receipts, and recomputed metrics into a tamper-evident cryptographic hash chain. The pre-registered decision rule selects the preferred path based on verified exceptions caught. Human approval records that a reviewer inspected the packet, with zero external actions taken. Anyone can verify the bundle offline."
- **On-Screen Captions**:
  - `TAMPER-EVIDENT EVIDENCE PACKET · PRE-REGISTERED DECISION RULE`
  - `APPROVAL GATE: EXTERNAL_ACTION_TAKEN: FALSE`

### Beat 8: Close & Verification (4:25 – 4:30 | 5s)
- **Visual**: Clean slide showing MIT License notice, Copyright (c) 2026 Larry D. Ross, GitHub repository URL, and offline CLI verification command: `python3 tools/verify_packet.py <bundle_dir>`.
- **Narration (LDR)**: "Distorted Reality. Sandboxed AI workflow execution with cryptographic evidence on Vultr."
- **On-Screen Captions**:
  - `MIT LICENSE · COPYRIGHT (C) 2026 LARRY D. ROSS`
  - `OFFLINE VERIFICATION: PYTHON3 TOOLS/VERIFY_PACKET.PY <BUNDLE_DIR>`

---

## Technical Audit & Safety Checklist
- [x] Runtime bounded: Exactly 4:30 planned runtime (strictly < 5:00).
- [x] Video opens on AP team workflow (R07 compliant).
- [x] Failure moment precedes containment moment (R10 compliant).
- [x] Attempt 2 executed on the same path that failed (M-A Part 2 / F2 compliant).
- [x] Zero API keys or secrets displayed in any console, UI, or slide frame.
- [x] Zero FFC route or fee strings.
- [x] Zero Darla / bakery branding or customer-order elements (AT-D1).
- [x] Zero prohibited claim phrases ("will improve", "guarantee", "proves ROI" per AT-25).
- [x] All real outcomes parameterized via {{placeholders}} until real run recording (F1 compliant).
