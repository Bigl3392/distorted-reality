# Evidence method

The council argues; the sandbox executes; the control plane checks. The numbers in the packet are recomputed by the control plane, never taken from a path's own report.

## The journal
One append-only JSON-lines file per run. Each entry has `seq` (0-based, gapless), a timestamp, the run id, a `kind`, an `actor`, a small `data` object, `prev_sha256` and `entry_sha256`. `entry_sha256` is the SHA-256 of the canonical JSON (sorted keys, no whitespace, ASCII only) of every other field; the first entry's `prev_sha256` is 64 zeros. Prompt and response bodies are not stored in the journal, only their hashes. Flipping any byte of any line breaks the chain at that line and the verifier names it.

## Pre-registration
The decision rule file is hashed and written to the journal before any sandbox is created. The packet carries the rule text and hash, and the verifier checks them against the journal and against the file.

## Claim-vs-evidence check
Each path returns a list of claims: for a case and a step, "this was resolved, and here is the evidence". A claim is **supported** only if all of these hold: the evidence exists; it belongs to the same case; it comes from the claimed step or an earlier one; it is not later in time than the claimed event; and its recorded status is completed. A claim whose only evidence is itself an unevidenced claim is unsupported. Anything else is unsupported or contradicted. A path with any unsupported or contradicted claim is ineligible. One bounded correction attempt is allowed.

## Metrics and the rule
The control plane recomputes `exceptions_caught`, `false_alarms`, `unsupported_claims` and `manual_touches` from the path's output and the sealed answer key. A path's self-reported numbers are kept in the receipt next to the recomputed ones, and any difference sets `metrics_discrepancy` instead of being reconciled. The pre-registered rule (`schemas/decision_rule.yaml`) says: a path is eligible only with a clean claim check, no unsupported claims and false alarms at most a stated fraction of cases; the best eligible path must beat the runner-up by a stated margin on exceptions caught, otherwise the result is `NO_SUFFICIENT_EVIDENCE`. A path whose final attempt ended in error or was killed is excluded, not counted as zero. The council's recommendation is shown beside the outcome; the rule's outcome stands.

## Verification
`tools/verify_packet.py` recomputes the journal chain, the packet hash, the frozen rule hash, the claim check from the stored events, the discrepancy flag and the rule's outcome as far as the packet allows (the answer key is not in the packet, so exceptions caught cannot be recomputed by an outside party). It prints `scan result: NOT INDEPENDENTLY RECOMPUTED` because the packet carries no intake answers by design. `[CONFIRM AT SUBMISSION: verifier results on the submitted packet]`
