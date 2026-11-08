"""Per-run state machine (spec section 3.3). No state skips. Any error becomes FAILED_CLOSED; terminal states never advance."""

TRANSITIONS = {
    "CREATED": ("DATASET_LOADED",),
    "DATASET_LOADED": ("MRI_DONE",),
    "MRI_DONE": ("SCAN_DONE",),
    "SCAN_DONE": ("COUNCIL_EVIDENCE",),
    "COUNCIL_EVIDENCE": ("COUNCIL_PATHS",),
    "COUNCIL_PATHS": ("COUNCIL_CRITIC",),
    "COUNCIL_CRITIC": ("COUNCIL_REVISION", "COUNCIL_DECISION"),
    "COUNCIL_REVISION": ("COUNCIL_DECISION",),
    "COUNCIL_DECISION": ("DECISION_RULE_FROZEN",),
    "DECISION_RULE_FROZEN": ("EXEC_PATH",),          # execution can only start after the rule is frozen
    "EXEC_PATH": ("EXEC_PATH", "CLAIM_CHECKED"),     # one entry per surviving path, sequential
    "CLAIM_CHECKED": ("EXEC_CORRECTION", "PACKET_BUILT"),
    "EXEC_CORRECTION": ("EXEC_CORRECTION", "PACKET_BUILT"),
    "PACKET_BUILT": ("AWAITING_APPROVAL",),
    "AWAITING_APPROVAL": ("APPROVED_VIEWED", "EXPIRED"),
}
TERMINAL = ("APPROVED_VIEWED", "EXPIRED", "FAILED_CLOSED")


class IllegalTransition(Exception):
    pass


class StateMachine:
    def __init__(self):
        self.state = "CREATED"
        self.failed_at = None
        self.failure_reason = None
        self.history = ["CREATED"]

    def advance(self, to):
        if self.state in TERMINAL:
            raise IllegalTransition(f"{self.state} is terminal")
        if to not in TRANSITIONS.get(self.state, ()):
            raise IllegalTransition(f"{self.state} -> {to} is not allowed")
        self.state = to
        self.history.append(to)
        return to

    def fail_closed(self, reason):
        if self.state in TERMINAL:
            raise IllegalTransition(f"{self.state} is terminal")
        self.failed_at = self.state
        self.failure_reason = reason
        self.state = "FAILED_CLOSED"
        self.history.append("FAILED_CLOSED")
