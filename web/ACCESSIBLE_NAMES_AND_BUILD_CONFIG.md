# M6 Web App: Accessible Names, Selectors & Build Configuration
**Author**: Johnny (Antigravity) — M6 Owner  
**Audience**: Walter (Codex) — M12 Validator / E2E Playwright Author  
**Date**: 2026-11-05  

---

## 1. Explicit Non-Mock Source & Build Configuration

### A. Environment Configuration
- The web app reads `import.meta.env.VITE_USE_MOCK`.
- Mock mode is **strictly opt-in**: mock code paths execute **only** when `VITE_USE_MOCK === 'true'`.
- Default for production builds and loopback integration: `VITE_USE_MOCK=false`.
- A `.env.production` file is committed in `workspace/distorted-reality/web/.env.production` pinning `VITE_USE_MOCK=false`.

### B. Clean Build Instructions
To build the distribution assets served by M5 (`web/dist`):
```bash
cd workspace/distorted-reality/web
npm ci
npm run build
```
This runs `vite build --mode production`. All built assets in `dist/` operate in live M5 mode.

### C. Dynamic Serving Origin & Port Binding
- When the built frontend in `web/dist` is served by `control.api.App` (or `launch_fake.py`), the browser connects to `http://127.0.0.1:<port>`, where `<port>` is the serving port (standard 8000 or an ephemeral port chosen by the launcher).
- The client dynamically reads `window.location.host` in the browser environment:
  - Provenance label: `M5 CONTROL WSGI (${originHost})`
  - Connection error message: `Connection to M5 server failed at ${url}. Is M5 WSGI running on ${originHost}?`
  - Heartbeat status on disconnect: `CONTROL: UNREACHABLE (${originHost})`
- The client uses root-relative API endpoints (`/healthz`, `/api/v1/...`). It makes zero external cross-origin calls and hardcodes no fixed port.

---

## 2. Accessible Names, ARIA Roles, and Test IDs Catalog

Playwright tests can reliably select elements either via accessible name (`page.getByRole(...)`, `page.getByLabel(...)`) or via explicit test IDs (`page.getByTestId(...)`).

### Header & Persistent Banner
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Text Content / Value |
|---|---|---|---|---|
| Synthetic Notice Bar | `div` | N/A | `synthetic-banner` | `SYNTHETIC DATA — SEED 20261103...` |
| Application Heading | `heading` (h1) | `DISTORTED REALITY` | N/A | `DISTORTED REALITY` |
| Data Source Provenance | `div` | `Explicit backend data source` | `data-source-provenance` | `DATA SOURCE: M5 CONTROL WSGI (127.0.0.1:<port>)` |
| Heartbeat Status | `div` | `Control plane heartbeat /healthz` | `heartbeat-status` | `CONTROL: HEALTHY` or `CONTROL: UNREACHABLE (<port>)` |
| Assurance Tier | `div` | N/A | `tier-badge` | `TIER: T1` |
| Recorded Runs Button | `button` | `Open Archived Recorded Runs` | `open-recorded-runs-btn` | `Recorded Runs` |

### Stage Progress Indicator
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Text Content / Value |
|---|---|---|---|---|
| Stage Progress Nav | `nav` | `Progress` | `stage-indicator` | Stages 1 through 5 |
| Stage 1 Step Pill | `div` | `Stage 1: Dataset & MRI` | `stage-step-1` | `1. MRI Scan` |
| Stage 2 Step Pill | `div` | `Stage 2: Intake & Scoring` | `stage-step-2` | `2. AP Assessment` |
| Stage 3 Step Pill | `div` | `Stage 3: Council & Blackbox` | `stage-step-3` | `3. Council & Sandbox` |
| Stage 4 Step Pill | `div` | `Stage 4: Packet Viewer` | `stage-step-4` | `4. Evidence Packet` |
| Stage 5 Step Pill | `div` | `Stage 5: Approval & Gate` | `stage-step-5` | `5. Human Approval` |

### Stage 1: Workflow Intake & Digital MRI
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Stage Heading | `heading` (h2) | `Deterministic AP Workflow Inventory` | N/A | Header card |
| Dataset Card Option | `button` (`div[role="button"]`) | `Select dataset eo-recv-v1` | `dataset-option-eo-recv-v1` | Click to select `eo-recv-v1` |
| Run MRI Button | `button` | `Load Dataset & Run Digital MRI` | `run-mri-btn` | Triggers `POST /runs`, then `POST /runs/{id}/mri` |
| MRI Results Heading | `heading` (h3) | `Digital MRI Inventory Result` | N/A | Rendered after MRI finishes |
| Determinism Badge | `span` | N/A | N/A | Text: `DETERMINISTIC (NO MODEL)` |
| MRI Steps Table | `table` | N/A | `mri-steps-table` | Contains 7 AP steps |
| Proceed to Stage 2 | `button` | `Proceed to Stage 2: AP Workflow Assessment` | `proceed-to-stage-2-btn` | Advances UI to Stage 2 |

### Stage 2: AP Team Workflow Intake & Scoring
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Stage Heading | `heading` (h2) | `Self-Assessment & Baseline Index` | N/A | Header card |
| Fill Reference Sample | `button` | `Fill Reference Sample` | `fill-reference-sample-btn` | Fills reference answers for all 15 questions |
| Question Container | `div` | N/A | `question-q_0` .. `question-q_14` | Individual question cards |
| Question Option Buttons | `button` | `Question {item_id} option {1..6}` | `q-{item_id}-opt-{1..6}` | e.g. `q-q_0-opt-4` |
| Submit Assessment Button | `button` | `Submit Assessment (15 Answers)` | `submit-intake-btn` | Triggers `POST /runs/{id}/intake` |
| Scan Results Card | `div` | N/A | `scan-results-card` | Rendered on 200 response |
| Overall Index Value | `div` | N/A | `overall-index-value` | Displays integer overall index (17–100) |
| Generic Recommendation | `p` | N/A | `generic-recommendation` | Displays generic AP recommendation |
| G5 Suppression Notice | `div` | N/A | `g5-suppression-notice` | Displays mandatory suppression limitation |
| Proceed to Stage 3 | `button` | `Proceed to Stage 3: Third Path Council & Execution` | `proceed-to-stage-3-btn` | Advances UI to Stage 3 |

### Stage 3: Third Path Council Deliberation & Blackbox
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Stage Heading | `heading` (h2) | `Multi-Model Deliberation & Interventions` | N/A | Header card |
| Convene Council Button | `button` | `Convene Council & Execute Blackbox` | `convene-council-btn` | Triggers `POST /runs/{id}/start` (enabled at `SCAN_DONE`) |
| Error / Refusal Banner | `div` | N/A | `stage3-error-banner` | Rendered on start error or 409 refusal |
| Evidence Agent Card | `div` | N/A | `council-evidence-card` | Facts extracted display |
| Path Agent Card | `div` | N/A | `council-path-card` | 3 distinct paths |
| Critic Agent Card | `div` | N/A | `council-critic-card` | Challenges & verdict display |
| Decision Agent Card | `div` | N/A | `council-decision-card` | Blinded neutral option evaluation |
| Proceed to Stage 4 | `button` | `Proceed to Stage 4: Packet Viewer & Verification` | `proceed-to-stage-4-btn` | Advances UI to Stage 4 |

### Stage 4: Evidence Packet & Sandbox Receipts
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Stage Heading | `heading` (h2) | `Deterministic Proof Layer` | N/A | Header card |
| Claim Discipline Banner | `div` | N/A | `claim-discipline-statement` | Displays exact schema claim sentence |
| Synthetic Notice Alert | `div` | N/A | `packet-synthetic-notice` | Displays exact `ALL DATA IN THIS PACKET IS SYNTHETIC.` notice |
| Incomplete Packet Alert | `div` | N/A | `incomplete-packet-alert` | Rendered only if run failed closed |
| Sandbox Run Receipts | `div` | N/A | `execution-receipts-container` | Container IDs, caps, termination, checks |
| Decision Rule Outcome Card | `div` | N/A | `decision-rule-card` | Normative rule outcome & preferred path |
| Council Qualitative Card | `div` | N/A | `council-qualitative-card` | Qualitative recommendation comparison |
| Recomputed Metrics Table | `table` | N/A | `recomputed-metrics-table` | Recomputed metrics across paths |
| Limitations Section | `div` | N/A | `limitations-section` | Container for assumptions, unknowns, did_not_prove & limitations |
| Assumptions Card | `div` | N/A | `packet-assumptions-card` | Displays exact governing assumptions |
| Unknowns Card | `div` | N/A | `packet-unknowns-card` | Displays exact operational unknowns |
| Did Not Prove Card | `div` | N/A | `packet-did-not-prove-card` | Displays exact `did_not_prove` array |
| Limitations Card | `div` | N/A | `packet-limitations-card` | Displays exact governing limitations |
| Proceed to Stage 5 | `button` | `Proceed to Stage 5: Human Approval Gate & Verification Downloads` | `proceed-to-stage-5-btn` | Advances UI to Stage 5 |

### Stage 5: Human Approval Gate & Verification Bundle
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Stage Heading | `heading` (h2) | `Controlled Human Review & Offline Verification` | N/A | Header card |
| Containment Notice | `div` | N/A | `containment-contract-notice` | Displays `EXTERNAL_ACTION_TAKEN: FALSE` |
| Mark Inspected Button | `button` | `Mark Packet as Inspected` / `Packet Inspected` | `view-packet-btn` | Triggers `POST /runs/{id}/approve` `{action: 'view'}` |
| Seal Approval Button | `button` | `Seal Human Approval` / `Human Review Confirmed` | `confirm-approval-btn` | Triggers `POST /runs/{id}/approve` `{action: 'confirm'}` |
| Generate Scoped Token | `button` | `Generate Scoped Token` | `generate-token-btn` | Triggers `POST /runs/{id}/download-link` |
| Download Packet | `link` (`a`) | `Download evidence_packet.json` | `download-link-packet` | Downloads `evidence_packet.json` |
| Download Journal | `link` (`a`) | `Download journal.jsonl` | `download-link-journal` | Downloads `journal.jsonl` |
| Download Events | `link` (`a`) | `Download events.json` | `download-link-events` | Downloads `events.json` |
| Download Rule | `link` (`a`) | `Download decision_rule.yaml` | `download-link-rule` | Downloads `decision_rule.yaml` |
| Copy Verify Command | `button` | `Copy verification command` | `copy-verify-cmd-btn` | Copies `python3 tools/verify_packet.py <bundle_dir>` |
| Verify Command Code | `code` | N/A | `verify-cmd-code` | Text: `python3 tools/verify_packet.py <bundle_dir>` |

### Archived Recorded Runs Modal
| Component / Element | ARIA Role / Tag | Accessible Name / Label | Test ID (`data-testid`) | Notes |
|---|---|---|---|---|
| Modal Dialog | `div` | N/A | `recorded-runs-modal` | Opened via header button |
| Close Modal Button | `button` | `Close recorded runs modal` | `close-recorded-modal-btn` | Closes modal |
| Cancel Button | `button` | `Cancel recorded runs selection` | `cancel-recorded-modal-btn` | Cancels selection |
| Recorded Run Item | `div` | `Recorded run {id}` | `recorded-run-{id}` | Click to select recorded run |
| Load Recorded Run Button| `button` | `Load Recorded Run` | `load-recorded-run-btn` | Loads selected recorded run |
| Empty Archive Notice | `div` | N/A | `empty-recorded-runs-msg` | Shown when archive has 0 runs |
