"""Evidence packet builder (EVIDENCE_SPEC sections 7 and 8). A pure function of its inputs: same inputs, same bytes (AT-10).

I-12 (decisions/DR-INT-001): packet_sha256 = SHA-256 of the canonical JSON (same form as the journal, I-10) of the packet WITHOUT
packet_sha256. `journal` covers the entries that precede the journal entry which records this packet's hash, so the packet can be built
before that entry is appended. A confirmed packet is a distinct rebuild (approval_gate.status VIEWED_CONFIRMED) with its own hash.
"""
import hashlib

from broker import _schemas

from .journal import canonical

CLAIM_STATEMENT = ("The calculation executed successfully under these assumptions. "
                   "This does not establish that any intervention will improve an actual business.")
SYNTHETIC_NOTICE = "ALL DATA IN THIS PACKET IS SYNTHETIC."
SUPPRESSION = "System-specific results are suppressed in public, by design, to protect the private association."
OVERALL_ONLY = "The deployed product computes only the overall index and performs no system-specific scoring."
DID_NOT_PROVE = ["that any intervention improves a real business",
                 "that the synthetic data represents any real operation",
                 "that the sandbox is immune to container-escape vulnerabilities"]
LIMITATIONS = [SUPPRESSION, OVERALL_ONLY, "Single dataset.", "Single seed.",
               "The council decision is qualitative only.",
               "Model non-determinism: council output is not reproducible byte-for-byte even at fixed prompts."]
ASSUMPTIONS = ["The dataset is synthetic and its injected faults are disclosed in the manifest.",
               "Metrics are recomputed by the control plane from exported events; path self-reports are not used.",
               "Paths are compared under the decision rule that was hashed and journaled before any execution."]
MEDIAN_UNKNOWN = ("median_cycle_min was not computed: the frozen specification defines no per-path resolution timing model, "
                  "so none was invented.")
FAILURE_STATES = {"CREATED", "DATASET_LOADED", "MRI_DONE", "SCAN_DONE", "COUNCIL_EVIDENCE", "COUNCIL_PATHS", "COUNCIL_CRITIC",
                  "COUNCIL_REVISION", "COUNCIL_DECISION", "DECISION_RULE_FROZEN", "CLAIM_CHECKED"}


class PacketError(Exception):
    pass


def packet_hash(p):
    body = {k: v for k, v in p.items() if k != "packet_sha256"}
    return hashlib.sha256(canonical(body).encode("ascii")).hexdigest()


def dumps(p):
    return canonical(p)


def _seal(p, schema):
    p["packet_sha256"] = packet_hash(p)
    errs = _schemas.errors(schema, p)
    if errs:
        raise PacketError("packet fails " + schema + ": " + errs[0])
    return p


def _header(c):
    return {"label": "SYNTHETIC", "packet_version": "1", "run_id": c["run_id"], "built_at": c["built_at"],
            "claim_statement": CLAIM_STATEMENT, "synthetic_notice": SYNTHETIC_NOTICE}


def build_packet(c):
    ex = c["executions"]
    if len(ex) < 2:
        raise PacketError("a complete packet needs at least 2 executions")
    ro = c["rule_outcome"]
    basis = ro["basis"]
    cid = c.get("council_recommended_path_id")
    if cid != ro["preferred_path_id"]:
        basis += (f" The council recommended {cid if cid else 'no path'}; the rule outcome stands.")
    unknowns = ["Behaviour on any real operation is unknown.", "Behaviour on other seeds or datasets is unknown."]
    if not c.get("median_cycle_computed"):
        unknowns.append(MEDIAN_UNKNOWN)
    p = _header(c)
    p.update({
        "assurance_tier": c["assurance_tier"],
        "dataset": c["dataset"], "mri": c["mri"], "scan": c["scan"], "council": c["council"],
        "decision_rule": {"sha256": c["rule"]["sha256"], "frozen_before_execution": True, "text": c["rule"]["text"]},
        "executions": ex,
        "outcome": {"result": ro["result"], "preferred_path_id": ro["preferred_path_id"], "basis": basis},
        "assumptions": list(ASSUMPTIONS), "unknowns": unknowns,
        "executed": [f"{e['path_id']} attempt {e['attempt']}: fresh container {e['sandbox_id']}, termination {e['termination']}, "
                     f"destroy verified {str(e['destroy_verified']).lower()}" for e in ex],
        "did_not_prove": list(DID_NOT_PROVE), "limitations": list(LIMITATIONS),
        "containment": c["containment"],
        "approval_gate": {"status": c["approval"]["status"], "external_action_taken": False, "confirmed_at": c["approval"]["confirmed_at"]},
        "journal": c["journal"],
    })
    return _seal(p, "evidence_packet.schema.json")


def _incomplete_basis(c):
    n = len(c.get("executions") or [])
    if n:
        return (f"Run failed closed after {n} execution receipt(s) were recorded; the decision rule was not applied, so no outcome was "
                "computed from them. The receipts are shown as recorded.")
    return "Run failed closed before any path was compared; no execution receipts exist."


def build_incomplete(c):
    if c["failed_at"] not in FAILURE_STATES and not (
            c["failed_at"].startswith(("EXEC_PATH_", "EXEC_CORRECTION_")) and c["failed_at"].rsplit("_", 1)[1].isdigit()):
        raise PacketError("failed_at is not a failure state")
    p = _header(c)
    p.update({
        "packet_status": "INCOMPLETE", "failed_at": c["failed_at"], "failure_reason": c["failure_reason"],
        "assurance_tier": c["assurance_tier"],
        "outcome": {"result": "NO_SUFFICIENT_EVIDENCE", "preferred_path_id": None, "basis": _incomplete_basis(c)},
        "assumptions": list(ASSUMPTIONS),
        "unknowns": ["Everything after the failure point is unknown.", "Whether a rerun would succeed is unknown."],
        "did_not_prove": list(DID_NOT_PROVE),
        "limitations": [f"Run failed closed at {c['failed_at']}: {c['failure_reason']}.", SUPPRESSION, OVERALL_ONLY],
        "approval_gate": {"status": "PENDING", "external_action_taken": False, "confirmed_at": None},
        "journal": c["journal"],
    })
    for k in ("dataset", "mri", "scan", "council", "decision_rule", "executions", "containment"):
        if k in c:
            p[k] = c[k]
    return _seal(p, "evidence_packet_incomplete.schema.json")
