"""Emit auditable synthetic contract logs; no detector/physical measurement."""
import hashlib
import json

from harness.zone_pair_status import FIELDS, PROFILE, PairStatusChannel
from tests.test_stall_observation_contract import FakePort, inputs, obs, stop


command, frames, check = inputs()
adapter = obs.ObservationAdapter("r1", enabled=True)
adapter.register_command(command)
adapter.record(command, frames, check)
bus = PairStatusChannel("pair-1")
a, b = FakePort(bus), FakePort(bus, "r2")
stop.synthetic_alarm_flow(a, task_id="pair-1", robot_id="r1", alarm_s=4.05)
stop.peer_abort_flow(b, task_id="pair-1", robot_id="r2", received_s=4.1)
wire_contract = dict(profile=PROFILE, fields=sorted(FIELDS), abort_state="abort",
                     conditions=["no_comm", "peer_ko", "leader_ko", "structured"])
print(json.dumps(dict(source="synthetic_only", live_binding_approved=False,
                      observation=adapter.rows, commands=adapter.command_summary,
                      stop_trace=a.trace, peer_stop_trace=b.trace, wire=bus.log,
                      own_events=a.events, peer_events=b.events,
                      next_decision_eligible=a.decisions,
                      wire_contract=wire_contract,
                      wire_contract_sha256=hashlib.sha256(obs.packed(wire_contract)).hexdigest(),
                      physics_sim_s=0, model_calls=0), indent=2))
