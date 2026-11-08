# Distorted Reality

> DRAFT. Every `[CONFIRM AT SUBMISSION: ...]` marker must be resolved or removed before this file is published. Nothing below may claim more than the submitted tree and its evidence show.

## 1. Summary

Distorted Reality takes **one synthetic team workflow** (accounts-payable reconciliation for a fictional hospitality group), inventories it read-only, asks 15 intake questions and reports an overall index with one generic recommendation, has a **council** of four model roles on Vultr Serverless Inference argue three materially different ways to run the workflow, **executes** the surviving paths in a destroyed-after-use sandbox against the same data, and produces an **evidence packet** that separates what was claimed from what was proven. The control plane recomputes the numbers itself and checks every completion claim against recorded evidence.

**What we claim, and nothing more:** the calculation executed successfully under these assumptions. This does not establish that any intervention will improve an actual business. All data is synthetic.

Challenge: **Blast Radius Zero** (sandboxed code execution). Product surface: **Future of Work**, a team workflow executed safely with proof. The containment and the proof layer are the submission evidence; the workflow is what a user sees.

## 2. Demo

- Live demo: `[CONFIRM AT SUBMISSION: public demo URL]`
- Video (under 5:00): `[CONFIRM AT SUBMISSION: video link]`
- Screenshot: `[CONFIRM AT SUBMISSION: path to a cleared screenshot]`

## 3. What it does

```
Dataset (synthetic) -> MRI (read-only inventory) -> Scan (15 answers -> overall index)
   -> Council (Evidence -> 3 Paths -> Critic -> at most one revision -> Decision on neutral labels)
   -> decision rule hashed and journaled  -> Blackbox (each surviving path, fresh container, destroyed after)
   -> claim-vs-evidence check + metric recompute -> Evidence packet -> Approval gate (view, confirm; no external action)
```

1. **MRI.** A deterministic, read-only inventory of the workflow (no model involved). It authorizes nothing.
2. **Scan.** 15 questions on a 1 to 6 scale. The result is an overall index and one fixed generic recommendation. Nothing else is computed or shown.
3. **Council.** Evidence states what the inputs support. Path proposes exactly three interventions that differ in ownership, order, checks or automation. Critic looks for strawmen, hidden constraint violations and overlap; an unreadable Critic reply counts as FAIL, never PASS. Path may revise once. Decision compares the survivors on shuffled neutral labels; "no winner" is a valid answer.
4. **Decision rule.** Before anything runs, the comparison rule is hashed and written to the journal. The council's opinion is shown beside the rule's outcome; the rule's outcome stands.
5. **Blackbox.** A Coder role turns each surviving path into a small Python function. It runs in a fresh container with no network and no secrets. One bounded correction is allowed when the claim check fails.
6. **Proof layer.** The control plane recomputes the metrics from the exported events and checks each completion claim: the evidence must exist, belong to the same case, come from the claimed step or an earlier one, and record a completed step.
7. **Packet and approval.** The packet is the only artifact that leaves the sandbox path. Approving it records that a human viewed it. **Approval takes no external action.**

## 4. Vultr services used

| Service | Use |
|---|---|
| Vultr Serverless Inference (`https://api.vultrinference.com/v1`) | Every model call by every council role and the Coder. One client class holds the only key; model ids are pinned per role in `models.example.yaml`; a response whose `model` differs from the requested id fails the run closed |
| Vultr Cloud Compute (control VM) | Runs the application, the broker, the journal and the approval gate |
| Vultr Cloud Compute (sandbox VM) | Secret-free host that runs the one-container-per-path sandbox; reachable only from the control VM `[CONFIRM AT SUBMISSION: single-VM variant if the sandbox shares the control VM]` |
| Vultr firewall group | Inbound rules as a second layer; the container's lack of network is enforced by Docker, not by the firewall |

Plan, region and OS: `[CONFIRM AT SUBMISSION: from the deployed console, not from this draft]`.

## 5. Architecture

See `docs/architecture.md` for the diagram. Two trust domains: the **control plane** (holds the inference key, the journal and the ground truth; never executes model-written code) and the **sandbox** (executes model-written code; holds no secret and no ground truth; no network).

Deployed assurance tier: `[CONFIRM AT SUBMISSION: T1 = container on a dedicated secret-free sandbox host plus a control VM; T0 = both on one VM, with a lower claim ceiling]`.

## 6. Containment

Each run creates one container, runs it once and destroys it. Flags include `--network none`, a read-only root filesystem, a small noexec tmpfs, `--cap-drop ALL`, `no-new-privileges`, a non-root user, memory with no swap, a pids limit, a CPU limit, a wall-clock deadline enforced by the controller and a watchdog timer, an output size cap, and no mounts, no environment inheritance and no device. The exact flag set is hashed into every receipt. A canary test checks that a secret placed in the controller's environment never appears inside the container, and a paired negative control proves the test can fail.

**Not claimed:** immunity to container-escape vulnerabilities, isolation equivalent to a separate machine, or protection against anything other than the tested payloads. See `docs/containment.md`.

## 7. Evidence packet

Fields and format: `docs/packet-format.md`. Method: `docs/evidence.md`. The journal is hash-chained and append-only. `tools/verify_packet.py` is an independent, stdlib-only verifier: it recomputes the journal chain, the packet hash, the frozen rule hash and the claim check, and exits non-zero on any mismatch.

```
python3 tools/verify_packet.py <bundle directory>     # packet.json, journal.jsonl, decision_rule.yaml, events.json
```

`[CONFIRM AT SUBMISSION: usage line matches the shipped verifier]`

## 8. Synthetic data statement

Every row is synthetic and generated from a fixed seed by the generator in `dataset/`. The faults injected into the data are disclosed in the manifest. The fictional entity is not a real business. The sealed answer key used for recomputation is generated at deploy time and is never committed.

## 9. What this does not prove

- That any intervention improves a real business.
- That the synthetic data represents any real operation.
- That the sandbox is immune to container-escape vulnerabilities.
- A preferred path is preferred **under these assumptions only**. When the evidence does not separate the paths, the result is "no sufficient evidence", which is a normal outcome.

## 10. Setup

Prerequisites: Python 3.12, Docker Engine `[CONFIRM AT SUBMISSION: exact version used]`, Node `[CONFIRM AT SUBMISSION: version from the lockfile]`.

```
cp .env.example .env          # on the control VM only; fill VULTR_INFERENCE_API_KEY and DR_OPERATOR_TOKEN yourself
cp models.example.yaml models.yaml   # set temperature and max_tokens per role; the app refuses to start while any value is UNSET
pip install -r requirements.txt
python3 -m unittest discover -s tests/unit -t .
python3 -I schemas/validate_schemas.py
python3 -I schemas/conformance_checks.py
```

`[CONFIRM AT SUBMISSION: build, run and deploy steps once they exist; do not list a step that has not been run]`

Limits are never defaulted. The per-run token cap, the daily token budget and the per-IP run limit are `UNSET` in the example and the public service refuses to make live model calls until they are set from a measured run; it then serves a labeled recorded run instead.

## 11. Reuse and originality disclosure

Distorted Reality applies methods first explored in earlier prototypes by the same author (a self-assessment scoring tool and a multi-agent council). The product code in this repository was written new during the event window (Nov 3-8, 2026), with AI coding agents under the author's direction; no prior source files are included.

## 12. Limitations

- System-specific results are suppressed in public, by design, to protect the private association.
- A single synthetic dataset and a single seed.
- The council's decision is qualitative; the numeric comparison is done by the pre-registered rule.
- Model output is not reproducible byte for byte, even at fixed prompts.
- `median_cycle_min` is not computed: the specification defines no per-path timing model and none was invented.
- Container-escape vulnerabilities are out of scope.

## 13. License

MIT. Copyright (c) 2026 Larry D. Ross. See `LICENSE`.
