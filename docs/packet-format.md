# Evidence packet format

Schema: `schemas/evidence_packet.schema.json` (complete) and `schemas/evidence_packet_incomplete.schema.json` (a run that failed closed). Every packet carries `label: "SYNTHETIC"` and the fixed claim statement: "The calculation executed successfully under these assumptions. This does not establish that any intervention will improve an actual business."

| Section | Content |
|---|---|
| Header | `label`, `packet_version`, `run_id`, `built_at`, `claim_statement`, `synthetic_notice`, `assurance_tier` (T0 or T1) |
| Inputs | `dataset` manifest, `mri` inventory, `scan` result (overall index, generic recommendation, optional keyed commitment to the answers, limitations) |
| Council | every role's output, the Critic's verdict and findings, the revision (none or one), the shuffle seed and label map, the qualitative decision, a per-call model-match record |
| Rule | `decision_rule`: hash, `frozen_before_execution: true`, text |
| Executions | at least two sandbox receipts, each numbered by attempt, with the recomputed and self-reported metrics, the discrepancy flag, the claim check and the journal head at that time |
| Outcome | `PATH_PREFERRED_UNDER_ASSUMPTIONS` or `NO_SUFFICIENT_EVIDENCE`, the preferred path or null, the basis (which also records any disagreement with the council and any excluded path) |
| Honesty | `assumptions`, `unknowns`, `executed`, `did_not_prove`, `limitations` |
| Containment | whether a stress test ran, how it terminated, the maximum health-check gap |
| Approval | `status` (`PENDING` or `VIEWED_CONFIRMED`), `external_action_taken` (always `false`), `confirmed_at` |
| Integrity | `journal.head_sha256`, `journal.entries`, `packet_sha256` |

## Hashing
`packet_sha256` is the SHA-256 of the canonical JSON (sorted keys, separators `,` and `:`, ASCII only) of the packet without the `packet_sha256` field. `journal` covers the entries that precede the entry which records the packet: entry number `journal.entries` has kind `packet_built` (or `approval` for the confirmed packet, or `error` for an incomplete one) and carries the packet hash. A confirmed packet is a separate packet with its own hash; the pending one stays valid.

## Incomplete packets
A run that cannot reach the packet stage still produces a packet: `packet_status: "INCOMPLETE"`, the state it failed in, the reason, only the sections that exist, outcome `NO_SUFFICIENT_EVIDENCE` with no preferred path (the basis states whether execution receipts exist and that the decision rule was not applied), and a limitation beginning "Run failed closed at". It cannot be approved.

## Verification bundle
`packet.json`, `journal.jsonl`, `decision_rule.yaml` and `events.json` (the dataset rows exactly as sent to the sandbox). The event rows' hash equals `events_sha256` in every receipt.
