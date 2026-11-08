"""Approval gate rules (DR-V08, AT-21). View the packet, then confirm. Approval takes NO external action: this module holds no
network object, no broker and no runner, and the orchestrator calls nothing outbound after it. Every approval entry carries
external_action_taken false."""


class ApprovalError(Exception):
    pass


def require_viewable(state, packet):
    if state != "AWAITING_APPROVAL":
        raise ApprovalError(f"run is {state}: only a run awaiting approval can be viewed for approval")
    if packet.get("packet_status") == "INCOMPLETE":
        raise ApprovalError("an incomplete packet cannot be approved")


def require_confirmable(state, viewed):
    if state != "AWAITING_APPROVAL":
        raise ApprovalError(f"run is {state}: it cannot be confirmed")
    if not viewed:
        raise ApprovalError("the packet must be viewed before it can be confirmed")
