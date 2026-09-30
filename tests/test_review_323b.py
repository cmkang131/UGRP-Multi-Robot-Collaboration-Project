"""Independent #323 verification; copy into the archived candidate before running.

No physics, rendering or provider calls. Role checks require the opt-in adapter.
F1's preserved counterexamples are strict xfails only on the exact known broken
source bytes; use --runxfail to reproduce their assertion failures. On the fixed
tree all checks must pass normally, with no xfails.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import math
import socket
import sys
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE_FIX_HOST_SHA256 = "7744d8ac00e9b0d4b95e71385c00f3dc6a652ca97f2d04e9f0d669a3c8647143"
IS_PRE_FIX = hashlib.sha256((ROOT / "harness/zone_own_team_host.py").read_bytes()).hexdigest() == PRE_FIX_HOST_SHA256
HAS_ROLE_ADAPTER = importlib.util.find_spec("harness.zone_pair_role_executor") is not None
requires_roles = pytest.mark.skipif(not HAS_ROLE_ADAPTER, reason="requires archived #323 fixed role adapter")
ASSIGNMENTS = tuple(itertools.permutations(("r1", "r2", "r3"), 2))
if HAS_ROLE_ADAPTER:
    from harness import zone_pair_role_executor as role_executor
    from harness import zone_pair_role_integration as integration
    from tests.test_zone_pair_role_exchange import setup, both, trial_for, release_action, ASSIGNMENTS
    from tests.test_zone_pair_executor import SHEETS, active
    from scripts import run_m2_pair as m2

    _source_receipt = lru_cache(maxsize=1)(role_executor.controller_source_record)


@pytest.mark.xfail(IS_PRE_FIX, strict=True, raises=AssertionError,
                   reason="F1: pre-fix #323 changed sealed v6e source bytes")
@pytest.mark.parametrize("name", ["zone_own_team_host", "zone_own_executor", "zone_pair_executor",
                                 "zone_pair_status", "zone_study_integration"])
def test_f1_sealed_source_counterexample(name):
    registration = json.loads((ROOT / "experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json").read_text())
    relative = f"harness/{name}.py"
    assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == registration["v6_contract"]["source_sha256"][relative]


@pytest.fixture(autouse=True)
def offline_and_cache_immutable_source_receipt(monkeypatch):
    for name in ("mujoco", "torch", "torchvision"):
        monkeypatch.setitem(sys.modules, name, None)

    def forbidden(*args, **kwargs):
        pytest.fail("review 323B prohibits network, simulation, rendering and inference")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    # All cases run on one immutable archive; cache only the AST/hash traversal.
    if HAS_ROLE_ADAPTER:
        monkeypatch.setattr(role_executor, "controller_source_record", _source_receipt)


def _expected_geometry(pose, role):
    """Independent rectangular-beam oracle, without production geometry helpers."""
    x, y, yaw = pose
    side = -1 if role == "end_neg" else 1
    c, s = math.cos(yaw), math.sin(yaw)
    heading = yaw if side == -1 else yaw + math.pi
    heading = (heading + math.pi) % (2 * math.pi) - math.pi
    pre = [x + side * .725 * c, y + side * .725 * s, heading]
    return pre, [
        ([x, y], [.30 * abs(c) + .02 * abs(s) + .06,
                  .30 * abs(s) + .02 * abs(c) + .06]),
        ([x - side * .425 * c, y - side * .425 * s], [.17, .17]),
        ([x - side * .725 * c, y - side * .725 * s], [.17, .17]),
    ]


@requires_roles
@pytest.mark.parametrize("roles", ASSIGNMENTS)
@pytest.mark.parametrize("pose", [(.8, 0., -.174533), (1., .1, 0.), (1.1, .1, .174533)])
def test_geometry_generalizes_beyond_original_sheet(roles, pose):
    host, _ = setup(factory=role_executor.m2_controller)
    sheet = copy.deepcopy(SHEETS["cargoX"])
    sheet["beam_xyyaw"] = list(pose)
    host.pairs.sheets["cargoX"] = sheet
    for rid, ep in both(host, roles).items():
        expected_pre, expected_keepouts = _expected_geometry(pose, roles.role(rid))
        driver = ep.controller.driver
        assert [*driver.goal, driver.goal_yaw] == pytest.approx(expected_pre)
        for actual in (ep.plan["keepouts"][rid], driver.keepouts):
            assert [k["id"] for k in actual] == [
                "order_sheet_beam", "partner_station", "partner_prestation"]
            for region, (center, extent) in zip(actual, expected_keepouts):
                assert region["center_m"] == pytest.approx(center)
                assert region["half_extents_m"] == pytest.approx(extent)


@requires_roles
@pytest.mark.parametrize("roles", ASSIGNMENTS)
def test_every_route_leg_uses_own_role_port_and_preserves_global_constants(roles):
    original_roles, original_door = copy.deepcopy(m2.ROLES), copy.deepcopy(m2.DOOR_PLAN)
    host, _ = setup(factory=role_executor.m2_controller)
    for rid, ep in both(host, roles).items():
        ctl = ep.controller
        assert ctl.rid == ep.port.own.robot_id == ep.status.robot_id == rid
        assert ctl.port is ep.port and ctl.arm.port is ep.port
        own_frame = ep.port.capture()
        assert own_frame["robot_id"] == rid
        sign = 1 if roles.role(rid) == "end_neg" else -1
        ctl.grasp_estimate = (1., .05, 0. if sign == 1 else math.pi)
        for seg, (a, b) in enumerate(zip(ep.plan["route"], ep.plan["route"][1:])):
            ctl.seg = seg
            start, end, command = ctl.door_schedule(10.)[-1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            if abs(dy) > 1e-6:
                assert command["forward"] == 0.
                assert command["left"] * dy * sign > 0.
            else:
                assert command["left"] == 0.
                assert command["forward"] * dx * sign > 0.
            assert end > start and command["turn"] == 0.
        assert ctl.rid == rid
    assert m2.ROLES == original_roles and m2.DOOR_PLAN == original_door


@requires_roles
@pytest.mark.parametrize("roles", ASSIGNMENTS)
def test_raw_four_condition_configs_and_actual_controllers_match(roles):
    runs = []
    for condition in integration.MAIN_CONDITIONS:
        host, _ = setup(factory=role_executor.m2_controller)
        trial = trial_for(host, condition, roles)
        for rid in roles.participants:
            assert release_action(trial, rid, roles.role(rid))["accepted"]
        eps = active(host)
        controllers = {rid: (ep.policy, ep.calibration_sha256, ep.plan,
                             type(ep.controller).__mro__[1:], type(ep.controller.driver),
                             ep.status.channel.heartbeat_timeout_s,
                             ep.status.channel.readiness_ttl_s)
                       for rid, ep in eps.items()}
        config = trial.study_config()
        # Do not reuse condition_invariant_config() as the oracle: compare raw
        # keys, allowing only communication topology/encoding/budget metadata.
        for key in ("condition", "topology", "encoding", "leader_id",
                    "inter_robot_channels", "dialogue_caps"):
            config.pop(key)
        runs.append((config, controllers))
    assert all(run == runs[0] for run in runs)


@requires_roles
@pytest.mark.parametrize("roles", ASSIGNMENTS)
@pytest.mark.parametrize("private_change", ["stopped", "holding", "pose", "busy"])
def test_initial_assignment_does_not_consult_unsubmitted_partner_state(roles, private_change):
    def run(change):
        host, exs = setup()
        actor, partner = roles.participants
        if change == "stopped":
            exs[partner].stopped = "PRIVATE_STOP"
        elif change == "holding":
            exs[partner]._holding_after = {"answer": "yes", "source": "private"}
        elif change == "pose":
            exs[partner].last_report = None
            exs[partner].last_obs = None
        elif change == "busy":
            assert host.call(partner, "hold", 1.)["accepted"]
        ack = host.call(actor, "pair_carry", "cargoX", "B", partner, roles.role(actor))
        assert ack["accepted"]
        ep = active(host)[actor]
        assert set(host.pairs.sessions[0]["endpoints"]) == {actor}
        assert ep.roles == roles and ep.partner_id == partner
        # Random task/job IDs are intentionally excluded; roles, admission and
        # the actual local controller decisions must be unchanged.
        return ep.plan, ep.arguments, ep.step(0.), ep.controller.state

    assert run(None) == run(private_change)
