# End-to-end validation plan — NOT_RUN

Owner: e2e module author. Independent validator remains PROPOSED, awaiting confirmation.
Scope: plan only until M6 and the M5 API exist. No page objects, endpoint names, selectors, dependencies or browser availability are assumed.

## Required owner inputs

M5: local loopback launch command, API contract, run/packet/download/approval routes and expiry semantics; network-denied fixture mode; deterministic negative/tie/incomplete runs.
M6: five-stage control names, accessible labels, loading/error behavior and the shared-vector display surface.
Scanner owner: approved private deny-list handling for copy checks, outside public source.
Operator: locally available browser binary and approved local port. No remote browser or live inference.
All fixtures must identify synthetic test data; a test fixture is never labeled a recorded real run.

## Expected rows (frozen before implementation)

| Row | Expected result | Status |
| --- | --- | --- |
| AT-01 | One bundled dataset; no upload control; owner-named upload endpoint returns 404 | NOT_RUN |
| AT-02 | MRI shows read-only/nothing-authorized inventory and unchanged dataset identity | NOT_RUN |
| AT-03 | Display all 76 shared scoring vectors exactly as backend returns; no browser scorer | NOT_RUN |
| AT-04 | Fourteen answers rejected; fifteen accepted; every result/packet shows required limitation | NOT_RUN |
| AT-G5-1 | API/DOM/download contain only the allowed overall result surface, no keyed answers/grouping | NOT_RUN |
| AT-G5-2/3 | Loopback fixture service: 2,000 vectors, fixed response shape and generic errors; size/timing by equal-sum permutations | NOT_RUN |
| AT-G5-4 | Visible text/screenshots/captions expose no scoring association or selection rules | NOT_RUN |
| AT-05, AT-D1, AT-25 | Approved copy scan; neutral AP workflow; no prohibited branding/claim language | NOT_RUN |
| AT-06/07 | Three paths visible; at most one revision; unusable Critic marked FAIL | NOT_RUN |
| AT-09/10 | Run receipts share dataset identity; downloaded packet passes the reassigned independent verifier | NOT_RUN |
| AT-11 | Tie/insufficient evidence displays no preferred path | NOT_RUN |
| AT-21 | Confirm viewed packet, approval records false external action; no action request emitted | NOT_RUN |
| AT-L2 | Unset/exhausted limits refuse inference; labeled genuine recorded packet only if one exists | NOT_RUN |
| Packet privacy | Run-scoped unguessable link expires; cross-run access refused | NOT_RUN |
| Failure | Incomplete packet shows reason and limitations; retry cannot skip frozen states | NOT_RUN |
| Accessibility smoke | All controls keyboard reachable, form labels present, SYNTHETIC DATA bar contrast measured | NOT_RUN |
| AT-20 | Public HTTPS fresh-browser run | NOT_RUN; separate deployment authorization required |

## Execution protocol once dependencies exist

Start from a clean local browser profile and record browser/version, exact source hashes, fixture identities and launch commands.
Block every network destination other than the explicitly selected loopback origin before opening the page.
Execute the full dataset → MRI → intake → council → execution → packet → approval flow, recording requests/responses and DOM evidence with no credentials.
Observe the approval request and ensuing traffic separately; distinguish UI polling from any external action request.
Test double-clicks, refresh/back navigation, refused transitions and expired download links without creating additional paid/live runs.
For equal-sum timing probes, interleave baseline/permuted requests and report distributions; do not invent a pass threshold.
Attach raw local evidence and exact row dispositions. Accessibility is a smoke check, not an audit.
No row becomes PASS merely because this plan exists.
