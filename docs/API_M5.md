# Control API (v1)

Status: built and author-tested against fakes; **not validated by anyone else, not run against a real sandbox or a real model**. Source: `control/api.py`. Everything is JSON unless noted. All data is synthetic. Base path `/api/v1`, **except `GET /healthz`, which is unprefixed** (and is the only route outside `/api/` besides the static files). Same-origin only; the SPA is served by the same process (`DR_STATIC_DIR`).

This document is a contract for the web app and the browser tests. Routes live in one place in the app; if a route here is wrong, tell the control-plane owner rather than coding around it.

## Flow (five stages, one run)
1. `GET /datasets` then `POST /runs` -> run created, dataset loaded, MRI done.
2. `GET /intake` then `POST /runs/{id}/intake` -> scan result (overall index + generic recommendation).
3. `POST /runs/{id}/start` -> council, then each surviving path in a fresh container, claim checks, packet. Asynchronous: poll `GET /runs/{id}`.
4. `GET /runs/{id}/council`, `/executions`, `/packet`, `/journal` as they become available.
5. `POST /runs/{id}/approve` `view`, then `confirm`. Approval takes **no external action**.

## Routes
| Method and path | Request | Success | Errors |
|---|---|---|---|
| `GET /healthz` | none | `200 {"ok": true}` | none. Polled by the heartbeat probe; must stay cheap |
| `GET /datasets` | none | `200 {"datasets": [{"dataset_id", "label": "SYNTHETIC", "case_count"}]}`. Always exactly one entry | none |
| `GET /intake` | none | `200 {"scale", "prompt", "items": [{"id", "text"} x15]}`. Opaque ids, flat list, in the shuffled order to display | none |
| `POST /runs` | `{"dataset_id": "<id from /datasets>"}` | `201 {"run_id", "state": "MRI_DONE", "mri": <mri_inventory>}` | `404` unknown dataset; `429` per-IP limit; `503` limits not configured (public mode), body carries `recorded_runs_url`; `413` body too large |
| `POST /runs/{id}/intake` | `{"answers": {"<question id>": 1..6, ... 15 entries}}` | `200 <scan_result>` (schema `scan_result.schema.json`; it never echoes answers) | `422 {"error": "15 integer answers in 1..6 required"}` for **every** kind of bad input, malformed JSON included; `409` wrong state; `404` unknown run |
| `POST /runs/{id}/start` | `{}` | `202 {"run_id", "state": "STARTED"}` | `409` wrong state or already started; `409 {"mode": "recorded", "recorded_runs": [...]}` when live inference is not available (see Recorded runs) |
| `GET /runs/{id}` | none | `200 {"run_id", "state", "history": [...], "label", "outcome"?, "failed_at"?, "failure_reason"?}` | `404` |
| `GET /runs/{id}/mri` `/scan` `/council` `/executions` `/packet` | none | `200` the section (`council_run`, a list of `blackbox_run` receipts, or the packet) | `404` not available yet |
| `GET /runs/{id}/journal` | none | `200 {"entries": [...]}` hash-chained entries (hashes and ids, no bodies) | `404` |
| `POST /runs/{id}/approve` | `{"action": "view"}` or `{"action": "confirm"}` | `200 {"packet": ...}`. `confirm` returns the **confirmed** packet (new hash, `approval_gate.status = VIEWED_CONFIRMED`, `external_action_taken: false`) | `400` bad action; `409` not viewable, not viewed yet, or run failed/expired |
| `POST /runs/{id}/download-link` | `{}` | `200 {"url": "/api/v1/download/<token>", "parts": {"packet", "journal", "events", "rule"} (full paths), "expires_in_seconds"}`. `url` is a **base, not a file**: `GET url` is `404`; use `parts` | `409` packet not viewed (an INCOMPLETE packet needs no view); `503` link lifetime not configured |
| `GET /download/{token}/packet` `/journal` `/events` `/rule` | none | `200` file (each request returns the **current** content, see Precedence and idempotency): the packet (or confirmed packet), `journal.jsonl`, `events.json`, `decision_rule.yaml` text. This is the verification bundle for `tools/verify_packet.py` | `404` unknown token; `410` expired |
| `GET /recorded-runs` | none | `200 {"recorded_runs": [{"recorded_run_id", "recorded_on", "run_id"}]}` | none |
| `GET /recorded-runs/{rec}` | none | `200 {"recorded": true, "label": "RECORDED REAL RUN", "recorded_run_id", "recorded_on", "packet"}` | `404` |
| `POST /operator/stress` | header `X-Operator-Token` | not built in this version: `501` with the operator token, `404` without. The stress test is operator-only and is never exposed publicly | |

Any other path under `/api/` is `404`; a known path with the wrong method is `405`. There is **no upload route** (`404` for every upload-like path). Anything outside `/api/` and `/healthz` is served as a static file from the SPA directory, with `index.html` as the fallback.

## Precedence and idempotency (fixed answers)
- **Order of checks on `POST /runs/{id}/intake`:** unknown run `404`, then body larger than 64 KiB `413`, then wrong run state `409`, then bad answers or malformed JSON `422` with the one generic text. So an oversized body is `413` on every route, intake included; the generic `422` covers everything else wrong with the answers. (The size is the only thing `413` reveals; it does not depend on the answers.)
- **`approve` `view`:** idempotent. The first call appends one `approval` journal entry (`viewed`); a repeat returns `200` with the same pending packet and appends nothing. After confirm or expiry, `view` is `409`.
- **`approve` `confirm`:** valid once. A repeat is `409` and changes nothing (same confirmed packet, same hash, no new journal entry). `confirm` before `view` is `409`.
- **Download tokens bind the run, not a packet version.** A token issued before confirmation stays valid until expiry. `packet` returns the confirmed packet if one exists, otherwise the pending one, at the time of the request; a pending packet downloaded earlier remains a valid packet. `journal` returns the whole journal at the time of the request; the journal only grows, and a packet covers a prefix of it (the entry right after the packet's `journal.entries` carries the packet's hash), so a packet and a longer journal fetched at different moments still verify together. `events` and `rule` are fixed once the run has started. Each `packet` download appends one `packet_downloaded` journal entry.
- **Failure after some execution:** an INCOMPLETE packet includes the receipts that were recorded. Its `outcome.basis` says the decision rule was not applied and no outcome was computed from them (it never says "no path was compared" when receipts exist).

## States (`state` and `history`)
`CREATED, DATASET_LOADED, MRI_DONE, SCAN_DONE, COUNCIL_EVIDENCE, COUNCIL_PATHS, COUNCIL_CRITIC, [COUNCIL_REVISION], COUNCIL_DECISION, DECISION_RULE_FROZEN, EXEC_PATH (per surviving path), CLAIM_CHECKED, [EXEC_CORRECTION], PACKET_BUILT, AWAITING_APPROVAL, APPROVED_VIEWED | EXPIRED`, and `FAILED_CLOSED` from any point. `label` is finer-grained than `state` (for example `EXEC_PATH_2`). On `FAILED_CLOSED` the run still has a packet: `GET /runs/{id}/packet` returns an INCOMPLETE packet (`packet_status: "INCOMPLETE"`, `failed_at`, `failure_reason`). Show it as a normal outcome, not a crash; its `outcome.basis` says what was and was not computed (see above). Fewer than 2 surviving paths ends the run the same way.

## What the UI must show or never show
- Show the packet's `claim_statement`, `synthetic_notice`, `assumptions`, `unknowns`, `did_not_prove`, `limitations` exactly as given. `NO_SUFFICIENT_EVIDENCE` is a first-class result.
- The council recommendation (`council.decision`) and the rule outcome (`outcome`) are shown side by side; the rule outcome stands. `outcome.basis` says when they differ.
- `median_cycle_min` may be absent from receipts; `unknowns` says why. Render absence, never a placeholder number.
- Never display or request anything system-specific. The scan result has `overall` (17..100), `recommendation`, `limitations` only.

## Polling and timing
`/start` returns at once. Poll `GET /runs/{id}` (the spec targets a full run in about 4 minutes; no polling interval is mandated here). `GET /healthz` is separate and unaffected by a running job.

## Limits and refusals (public mode)
No numeric limit is baked into the code. The per-IP run limit (`DR_RATE_LIMIT_RUNS_PER_IP_PER_HOUR`) and the download-link lifetime (`DR_PACKET_LINK_TTL_SECONDS`) are `UNSET` until LDR approves values; while `UNSET`, creating runs and issuing links are refused (`503`) in public mode. The UI should treat `503` and `429` as ordinary states and offer the recorded run.

## Recorded runs
When live inference is unavailable (limits UNSET or budget exhausted), `POST /runs/{id}/start` answers `409` with `"mode": "recorded"`. Recorded runs are real packets that an operator placed in the recorded-runs directory; the API serves one only if it validates against `evidence_packet.schema.json` and its `packet_sha256` recomputes. The list can be empty; the API never fabricates one. Always label it "RECORDED REAL RUN" with its date.

## Security notes
Responses carry `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; static files add `Content-Security-Policy: default-src 'self'`. Request bodies over 64 KiB are refused (`413`). Error bodies contain no paths or stack traces. The client IP is used only as a hashed rate-limit bucket in memory and is never journaled. The forwarded-for header is trusted only when `DR_TRUST_PROXY=1` (behind the reverse proxy).
