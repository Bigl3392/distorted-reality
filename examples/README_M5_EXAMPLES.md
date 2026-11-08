# M5 example bundles (fake-backed)
Two bundles written by the real M5 orchestrator (`control/orchestrator.py`) during a loopback run of `tests/fakes/launch_fake.py`, then copied unchanged. **They are not recordings of a real run:** the model server, runner and dataset are test doubles, the answers are all 3, the key is a fake. They exist so `tools/verify_packet.py` can be checked against packets the orchestrator itself produced (Peggy Sue's note: no M5 bundle had been verified). They are not recorded runs for the product and must not be shown as such.

| Directory | Scenario | Run state | Verifier (Linux, Python 3.14.4, pinned deps) |
|---|---|---|---|
| `m5_complete_fake_backed/` | `complete` | AWAITING_APPROVAL, viewed and confirmed (`packet.json` pending, `packet_confirmed.json` distinct rebuild) | exit 0, no FAIL; ground-truth metrics and `median_cycle_min` NOT CHECKED (by design, I-9) |
| `m5_incomplete_fake_backed/` | `incomplete` | FAILED_CLOSED at COUNCIL_EVIDENCE, INCOMPLETE packet | exit 0; rule file NOT CHECKED (I-16) |

Run: `python3 tools/verify_packet.py examples/m5_complete_fake_backed` (one bundle directory). Verifier output is in `00_Testing/distorted-reality_Private/runs/T-013_M5-example-bundles_linux_2026-11-05/`. This is author-side agreement evidence, not a validation of M5 or M9.
