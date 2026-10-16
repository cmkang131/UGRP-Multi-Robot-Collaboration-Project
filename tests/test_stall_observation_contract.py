"""Synthetic NumPy/ports only. No simulator, image inference or model calls."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import pickle
import random
import sys
import socket

import numpy as np
import pytest

from harness.zone_pair_status import FIELDS, PROFILE, PairStatusChannel, PairStatusEndpoint

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "experiments/2026-09-30-p08-stall-contract"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


obs = load("observation_contract")
stop = load("fake_stop_contract")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("P08 must never contact a model or network endpoint")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def inputs(command_id="c1", speed=.005):
    command = obs.OwnCommand("r1", command_id, 0., 6., speed, 0.)
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    frames = tuple(obs.OwnFrame("r1", "wrist_rgb", f"r1-{i}", t, rgb) for i, t in enumerate((3., 3.9, 4.)))
    check = obs.FakeCheck(4., 4.05, "STALL_SUSPECT", 3., 1., .1, tuple(f.frame_id for f in frames))
    return command, frames, check


def test_observation_default_off_and_enabled_bytes_unchanged():
    command, frames, check = inputs()
    bus = PairStatusChannel("task")
    ep = PairStatusEndpoint(bus, "r1")
    ep.tick("carry", 4.)
    controller = dict(commands=[b"queued base", b"queued arm"], state="carry")
    before = pickle.dumps((controller, bus.__dict__, random.getstate(), np.random.get_state()))
    pixels = frames[0].rgb.tobytes()
    for enabled in (False, True):
        recorder = obs.ObservationAdapter("r1", enabled=enabled)
        assert recorder.record(command, frames, check) is None
        assert recorder.command_denominator == int(enabled)
        assert len(recorder.rows) == int(enabled)
        assert pickle.dumps((controller, bus.__dict__, random.getstate(), np.random.get_state())) == before
        assert frames[0].rgb.tobytes() == pixels and frames[0].rgb.flags.writeable
    row = recorder.rows[0]
    assert row["frame_id"] == "r1-2" and row["selected_frame_ids"] == ["r1-0", "r1-1", "r1-2"]
    assert row["baseline_age_s"] == 1. and row["noise_floor"] == .1
    assert row["alarm_s"] == 4. and row["available_s"] == 4.05
    assert row["command"]["forward_mps"] == .005 and row["denominator_included"]
    row["command"]["forward_mps"] = 99
    assert recorder.rows[0]["command"]["forward_mps"] == .005


@pytest.mark.parametrize("state", sorted(obs.STATES - {"STALL_SUSPECT", "NO_STALL_SUSPECT"}))
def test_unknowns_and_short_low_speed_windows_stay_in_denominator(state):
    command, _, check = inputs()
    if state == "UNSUPPORTED_SHORT_COMMAND":
        command = replace(command, end_s=4.5)
    adapter = obs.ObservationAdapter("r1", enabled=True)
    adapter.record(command, (), replace(check, state=state, selected_frame_ids=(), baseline_end_s=None))
    assert adapter.command_denominator == 1
    assert adapter.rows[0]["state"] == state and adapter.rows[0]["unknown"]
    assert adapter.rows[0]["alarm_s"] is None
    assert adapter.command_summary[0]["unarmed"]


def test_registered_command_without_any_check_is_unarmed_not_dropped():
    command, _, _ = inputs()
    adapter = obs.ObservationAdapter("r1", enabled=True)
    adapter.register_command(command)
    assert adapter.command_denominator == 1
    assert adapter.command_summary == ({"command_id": "c1", "checks": 0, "armed_checks": 0,
                                         "unknown_checks": 0, "unarmed": True, "status": "NO_CHECKS"},)


def test_retrospective_coverage_failure_keeps_causal_alarm_and_unknown():
    command, frames, check = inputs()
    adapter = obs.ObservationAdapter("r1", enabled=True)
    adapter.record(command, frames, replace(check, interval_status="INSUFFICIENT_COVERAGE"))
    row = adapter.rows[0]
    assert row["alarm_s"] == 4. and row["state"] == "STALL_SUSPECT"
    assert row["interval_status"] == "INSUFFICIENT_COVERAGE" and row["unknown"]
    assert row["armed"] and not adapter.command_summary[0]["unarmed"]


def test_observation_on_off_fake_execution_trace_and_rng_bytes_match():
    saved = random.getstate(), np.random.get_state()
    traces = []
    try:
        for enabled in (False, True):
            random.seed(1908)
            np.random.seed(1908)
            bus = PairStatusChannel("task")
            endpoint = PairStatusEndpoint(bus, "r1")
            adapter = obs.ObservationAdapter("r1", enabled=enabled)
            commands, states = [], []
            for index in range(3):
                command, frames, check = inputs(f"c{index}")
                commands.append(dict(forward=random.random(), pulse=int(np.random.randint(1000, 2000))))
                endpoint.tick("carry", float(index))
                states.append(dict(phase="carry", queue=list(commands)))
                adapter.record(command, frames, replace(check, state=("REFERENCE", "NO_STALL_SUSPECT", "STALL_SUSPECT")[index]))
            traces.append(pickle.dumps((commands, states, bus.log, random.getstate(), np.random.get_state())))
        assert traces[0] == traces[1]
    finally:
        random.setstate(saved[0])
        np.random.set_state(saved[1])


@pytest.mark.parametrize("change,reason", [
    ({"robot_id": "r2"}, "FOREIGN_INPUT"), ({"camera": "top_rgb"}, "FOREIGN_INPUT"),
    ({"captured_s": float("nan")}, "DISCONTINUOUS_TIME"),
    ({"captured_s": 5.}, "DISCONTINUOUS_TIME"),
    ({"frame_id": ["wrong"]}, "DISCONTINUOUS_TIME"),
    ({"rgb": np.zeros((2, 2), dtype=np.uint8)}, "INVALID_RGB"),
])
def test_forbidden_or_invalid_frames_cannot_be_scored(change, reason):
    command, frames, check = inputs()
    adapter = obs.ObservationAdapter("r1", enabled=True)
    adapter.record(command, (replace(frames[0], **change), *frames[1:]), check)
    assert adapter.rows[0]["state"] == "UNKNOWN_INPUT"
    assert adapter.rows[0]["reason"] == reason and adapter.command_denominator == 1


@pytest.mark.parametrize("key", ["gt_displacement", "contact", "peer_frame", "actual_joints", "simulator", "pose"])
def test_input_schema_has_no_truth_or_peer_slots(key):
    command, frames, _ = inputs()
    with pytest.raises(TypeError):
        obs.OwnCommand(**{**obs.asdict(command), key: object()})
    with pytest.raises(TypeError):
        obs.OwnFrame(robot_id="r1", camera="wrist_rgb", frame_id="f", captured_s=1., rgb=frames[0].rgb, **{key: object()})


def test_duplicate_reverse_time_and_input_fault_remain_unknown():
    command, frames, check = inputs()
    adapter = obs.ObservationAdapter("r1", enabled=True)
    adapter.record(command, frames[::-1], check)
    adapter.record(command, frames, check)
    adapter.record(command, frames, replace(check, scheduled_s=float("nan")))
    assert adapter.command_denominator == 1 and len(adapter.rows) == 3
    assert all(row["state"] == "UNKNOWN_INPUT" for row in adapter.rows)
    assert all(row["denominator_included"] for row in adapter.rows)


def test_provenance_cannot_be_missing_future_or_reassigned():
    command, frames, check = inputs()
    for change in ({"selected_frame_ids": ()}, {"selected_frame_ids": (["wrong"],)},
                   {"state": []}, {"baseline_end_s": 4.1}, {"noise_floor": -1.}):
        adapter = obs.ObservationAdapter("r1", enabled=True)
        adapter.record(command, frames, replace(check, **change))
        assert adapter.rows[0]["state"] == "UNKNOWN_INPUT"
    with pytest.raises(ValueError, match="reused"):
        adapter.record(replace(command, end_s=7.), frames, check)
    with pytest.raises(ValueError, match="own issued"):
        adapter.record(replace(command, robot_id="r2"), frames, check)


class FakePort:
    fake_only = True

    def __init__(self, bus, rid="r1", failure=None):
        self.task_id, self.robot_id = bus.task_id, rid
        self.endpoint = PairStatusEndpoint(bus, rid)
        self.now, self.terminal, self.failure = 4., False, failure
        self.timeline = ["base", "arm"]
        self.trace, self.events, self.decisions = [], [], []

    def mark(self, kind, now):
        self.trace.append((kind, now))
        if kind == self.failure:
            raise RuntimeError(kind)

    def cancel_own_scheduled(self, now):
        self.mark("cancel", now)
        self.timeline.clear()

    def hold_own(self, now):
        assert not self.timeline
        self.mark("hold", now)

    def publish_abort(self, now):
        self.mark("enum", now)
        self.endpoint.tick("abort", now)

    def fail_own_job(self, now, reason):
        self.mark("own_event", now)
        event = dict(robot_id=self.robot_id, event="job_failed", sim_s=now,
                     scheduler_trigger="failure", detail={"reason": reason})
        self.events.append(event)
        return event

    def next_decision_eligible(self, event, now):
        # Fake admission only: a busy/budget-limited real scheduler can defer/refuse.
        assert event["robot_id"] == self.robot_id
        self.mark("decision_eligible", now)
        self.decisions.append((self.robot_id, now))
        return now


@pytest.mark.parametrize("condition", ["no_comm", "peer_ko", "leader_ko", "structured"])
def test_synthetic_alarm_own_cancel_hold_enum_event_and_next_decision(condition):
    bus = PairStatusChannel("pair-1")
    a, b = FakePort(bus), FakePort(bus, "r2")
    peer_before = pickle.dumps((b.timeline, b.events, b.decisions))
    eligible = stop.synthetic_alarm_flow(a, task_id="pair-1", robot_id="r1", alarm_s=4.05)
    assert eligible == 4.05
    assert a.trace == [(k, 4.05) for k in ("cancel", "hold", "enum", "own_event", "decision_eligible")]
    assert pickle.dumps((b.timeline, b.events, b.decisions)) == peer_before
    wire = bus.log[-1]
    assert set(wire) == FIELDS and wire["state"] == "abort" and PROFILE == "zone_pair_status_v5"
    assert all(wire[k] is None for k in ("frame_id", "observed_at_s", "ready_until_s"))
    assert "SYNTHETIC" not in json.dumps(wire)
    # Peer independently reads only the existing enum, then stops its own queue.
    assert bus.partner_view("r2", 4.1)["r1"]["state"] == "abort"
    stop.peer_abort_flow(b, task_id="pair-1", robot_id="r2", received_s=4.1)
    assert not b.timeline and b.events[0]["robot_id"] == "r2"
    assert b.events[0]["detail"]["reason"] == "PARTNER_ABORT"
    before = pickle.dumps((a.trace, bus.log, a.events, a.decisions))
    assert stop.synthetic_alarm_flow(a, task_id="pair-1", robot_id="r1", alarm_s=4.1) is None
    assert pickle.dumps((a.trace, bus.log, a.events, a.decisions)) == before


@pytest.mark.parametrize("failure", ["cancel", "hold", "enum", "own_event"])
def test_fake_flow_failures_do_not_claim_next_decision(failure):
    port = FakePort(PairStatusChannel("pair-1"), failure=failure)
    with pytest.raises(RuntimeError, match=failure):
        stop.synthetic_alarm_flow(port, task_id="pair-1", robot_id="r1", alarm_s=4.1)
    assert not port.decisions


@pytest.mark.parametrize("task,rid,at", [("other", "r1", 4.), ("pair-1", "r2", 4.), ("pair-1", "r1", 3.)])
def test_fake_alarm_rejects_wrong_job_actor_or_stale_time(task, rid, at):
    port = FakePort(PairStatusChannel("pair-1"))
    with pytest.raises(ValueError):
        stop.synthetic_alarm_flow(port, task_id=task, robot_id=rid, alarm_s=at)
    assert not port.trace


def test_fake_alarm_requires_fake_port_and_finite_clock():
    port = FakePort(PairStatusChannel("pair-1"))
    for at in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            stop.synthetic_alarm_flow(port, task_id="pair-1", robot_id="r1", alarm_s=at)
    port.fake_only = False
    with pytest.raises(ValueError, match="fake port"):
        stop.synthetic_alarm_flow(port, task_id="pair-1", robot_id="r1", alarm_s=4.)
    assert not port.trace


@pytest.mark.parametrize("budget_spent", [False, True])
def test_own_failure_reaches_real_scheduler_rate_and_budget_gates_on_fake_wire(budget_spent):
    from harness.zone_event_scheduler import ReplayTransport
    from harness.zone_study_decisions import DecisionLimits, DecisionScheduler
    from harness.zone_sim_cost import CostParams
    transport = ReplayTransport({})  # ScriptedWire, never sockets/providers.
    spent = [False]
    scheduler = DecisionScheduler(transport, own_job=lambda rid: None,
                                  decision_limits=DecisionLimits(), start_s=3.,
                                  cost_params=CostParams(call_overhead_s=.1),
                                  external_budget_spent=lambda: spent[0])
    scheduler.trigger("r1", "start", at=3.)
    scheduler.run(until_s=4., close_at_horizon=False)
    assert len(scheduler.calls) == 1
    spent[0] = budget_spent
    port = FakePort(PairStatusChannel("pair-1"))

    def eligible(event, now):
        port.mark("decision_eligible", now)
        scheduler.trigger(event["robot_id"], event["scheduler_trigger"], at=now)
        scheduler.available(event["robot_id"], at=now)
        return now

    port.next_decision_eligible = eligible
    assert stop.synthetic_alarm_flow(port, task_id="pair-1", robot_id="r1", alarm_s=4.1) == 4.1
    scheduler.run(until_s=4.9, close_at_horizon=False)
    assert len(scheduler.calls) == 1  # last 3.0 + min interval 2.0; no immediate model decision.
    scheduler.run(until_s=5.2, close_at_horizon=False)
    if budget_spent:
        assert len(scheduler.calls) == 1
        assert any(e["event"] == "pilot_budget_exhausted" for e in scheduler.decision_events)
    else:
        assert len(scheduler.calls) == 2
        assert scheduler.calls[-1].started_sim_s == 5.
    assert all(call.actor == "r1" for call in scheduler.calls)


def test_draft_modules_have_no_runtime_consumers_or_forbidden_dependencies():
    import ast
    for name in ("observation_contract", "fake_stop_contract"):
        tree = ast.parse((HERE / (name + ".py")).read_text())
        modules = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                   for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        assert modules <= {"dataclasses", "hashlib", "json", "math", "numpy"}
        for directory in ("harness", "sim", "scripts"):
            for path in (ROOT / directory).glob("*.py"):
                if path.name != "run_ci_tests.py":
                    source = path.read_text()
                    imports = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                               for node in ast.walk(ast.parse(source))
                               if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
                    assert not any(module == name or (module and module.endswith("." + name)) for module in imports), path
                    assert "2026-09-30-p08-stall-contract" not in source, path
