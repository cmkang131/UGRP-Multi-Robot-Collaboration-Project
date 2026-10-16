"""Executable DRAFT ordering contract for fake ports ONLY; no runtime binding.

An existing fixed 'abort' enum carries no D1 score/reason/frame to the peer.
Real cancellation acknowledgement, actuation and scheduler admission are NOT
implemented by this fake. The first error propagates; later steps must not run.
"""
import math


def synthetic_alarm_flow(port, *, task_id, robot_id, alarm_s):
    """Fake alarm -> own cancel -> hold -> enum -> own event -> eligibility.

    The caller must be a test-owned fake port. No detector output is accepted.
    A production implementation needs independent review in a separate PR.
    """
    return _stop(port, task_id, robot_id, alarm_s, "D1_STALL_SUSPECT_SYNTHETIC")


def peer_abort_flow(port, *, task_id, robot_id, received_s):
    """Fake peer polls existing STATUS; it receives no D1 reason or image."""
    if not any(v["state"] == "abort" for v in port.endpoint.channel.partner_view(robot_id, received_s).values()):
        return None
    return _stop(port, task_id, robot_id, received_s, "PARTNER_ABORT")


def _stop(port, task_id, robot_id, alarm_s, reason):
    if getattr(port, "fake_only", False) is not True:
        raise ValueError("fake port required; live binding is not approved")
    if (task_id, robot_id) != (port.task_id, port.robot_id):
        raise ValueError("alarm task/robot mismatch")
    if port.terminal:
        return None
    if type(alarm_s) not in (int, float) or not math.isfinite(alarm_s) or alarm_s < port.now:
        raise ValueError("stale synthetic alarm")
    port.cancel_own_scheduled(alarm_s)
    port.hold_own(alarm_s)
    port.publish_abort(alarm_s)
    event = port.fail_own_job(alarm_s, reason)
    port.terminal = True
    return port.next_decision_eligible(event, alarm_s)
