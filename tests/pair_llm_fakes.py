"""Offline stand-ins for the pair LLM loop tests: a fake physics owner that renders no image of a world.

``FakeBackend`` has the interface the case loop uses of ``sim.final_pair_v3.PhysicsBackend``. Its frames are
small synthetic JPEGs of the right shape (the real executors and providers consume them); the beam
trajectory is a script, written to ``eval_only/trajectory.jsonl`` exactly like the real owner writes it.
"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from harness import zone_final_pair_contract as c

SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
BEAM_START = [1.0, 0.05, 0.03]


class FakeBackend:
    truth = None

    def __init__(self, bundle, out, *, seed, beam=None):
        self.out, self.bundle, self.seed = Path(out), bundle, seed
        self.now, self.closed, self.deadline = 0., False, None
        self.actions, self.samples, self.captures = [], [], 0
        self.commands = {r: dict(SERVO) for r in c.ROBOTS}
        self.beam = beam or (lambda t: BEAM_START)
        self._frame = {r: 0 for r in c.ROBOTS}

    def reset(self, cap):
        self.now = 1.
        return self.now

    def set_deadline(self, t):
        self.deadline = t

    def advance_to(self, t):
        assert self.now <= t <= self.deadline + 1e-9
        self.now = t

    def issue(self, rid, action):
        self.actions.append((round(self.now, 6), rid, copy.deepcopy(action)))

    def eval_sample(self):
        self.samples.append(self.now)
        path = self.out / 'eval_only' / 'trajectory.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as stream:
            stream.write(json.dumps({'t': self.now, 'beam_xyz_m': list(self.beam(self.now)),
                                     'physical_success': None}) + '\n')

    def capture(self):
        self.captures += 1
        out = {}
        for rid in c.ROBOTS:
            self._frame[rid] += 1
            number = self._frame[rid]
            pixels = np.zeros((480, 640, 3), np.uint8)
            pixels[..., 0] = np.linspace(0, 255, 640, dtype=np.uint8)[None, :]
            pixels[..., 1] = (number * 7) % 256
            pixels[..., 2] = 60 if rid == 'r1' else 180
            buf = io.BytesIO()
            Image.fromarray(pixels).save(buf, 'JPEG', quality=60)
            jpeg = buf.getvalue()
            obs = {'robot_id': rid, 'frame_id': number, 'sim_time': self.now, 'camera': 'robot_cam',
                   'image': base64.b64encode(jpeg).decode('ascii'), 'sha256': hashlib.sha256(jpeg).hexdigest(),
                   'actuator_state': {'motor_commands': [0, 0, 0, 0], 'servo_pulses': {}}}
            out[rid] = (obs, np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))
        return out

    def close(self):
        self.closed = True


def delivered_beam(t):
    """A scripted beam: lifted, carried into zone B (static map centre), set down (judge fixture only)."""
    if t < 3.:
        return BEAM_START
    if t < 6.:
        return [BEAM_START[0], BEAM_START[1], BEAM_START[2] + .10]
    return [4.6, -2.1, BEAM_START[2]]


# ---------------------------------------------------------------------------
# shared fixtures and builders

import socket
import sys

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_inputs as pi
from harness import pair_llm_plumbing as plumbing
from harness import zone_map_schematic as ms
from harness.pair_llm_runtime import GatedRuntime
from harness.zone_study_inputs import belief_skeleton, static_map_for_call


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **kw: pytest.fail('real worker forbidden'))


def map_bundle():
    return ms.map_bundle(contract.read_registry()['map_id'], landmark_detail='none')


def make_inputs(condition='peer_nl', rid='r1', *, request_id='req_t1', inbox=None, history=(), t=0., frame_no=1):
    """A validated ``PairInputs`` from the real scenario, map bundle and a fake own frame."""
    from harness.pair_llm_dispatch import map_figure
    bundle = map_bundle()
    source = pi.PairSheetSource(contract.scenario(), bundle)
    backend = FakeBackend({}, '/nonexistent', seed=0)
    backend.now = t
    obs, _ = backend.capture()[rid]
    jpeg = base64.b64decode(obs['image'])
    payload = pi.build_payload(
        robot_id=rid, condition=condition, request_id=request_id, sim_time_s=t,
        static_map=static_map_for_call(bundle), order_sheet=source.sheet(),
        own_rgb_refs=[pi.own_rgb_ref(rid, frame_no, t, obs['sha256'])], own_command_history=list(history),
        self_belief=belief_skeleton(), inbox=inbox, pinned=source.pinned)
    png, _ = map_figure(bundle)
    return pi.PairInputs(payload, jpeg, png, source.pinned), source, bundle


def synthetic_cal(tmp_path, name='cal'):
    return plumbing.synthetic_calibration(Path(tmp_path) / f'{name}.json')


def ready(runtime, now=0.):
    """TEST ONLY: make both executors report an available pose so ``Team.start`` can accept (the blind
    plumbing provider never converges). The same injection as ``test_zone_final_pair_v3``."""
    from harness.owncam_pose_source import PoseReport
    from tests.test_zone_pair_executor import pair_obs
    for rid, own in runtime.actors.items():
        own.last_obs = pair_obs(rid, 1, now, SERVO)
        own.last_report = PoseReport(now, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01,
                                     source=own.pose.source)
        own.gate.state = 'ok'


class ReadyRuntime(GatedRuntime):
    """TEST ONLY: ``GatedRuntime`` whose idle robots always report an available pose after each frame."""

    def on_frames(self, now, frames):
        super().on_frames(now, frames)
        from harness.owncam_pose_source import PoseReport
        for own in self.actors.values():
            if own.job is None:
                own.last_report = PoseReport(now, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01,
                                             std_yaw_rad=.01, source=own.pose.source)
                own.gate.state = 'ok'


def gated_runtime(tmp_path, *, seed=911, cls=GatedRuntime):
    cal = synthetic_cal(tmp_path)
    static = c.resolve(contract.read_registry()['map_id'])[0]
    runtime = cls(static, cal['path'], cal['sha256'], seed=seed, provider_factory=plumbing.blind_provider_factory)
    runtime.initial_commands(0., {r: dict(SERVO) for r in c.ROBOTS})
    return runtime


def run_arm(tmp_path, condition, model=None, *, cap_s=12., runtime_factory=None, name=None, backend=FakeBackend):
    """One arm through ``run_pair_case`` on the fake physics. Returns ``(result, out_dir, model)``."""
    from harness.pair_llm_case import run_pair_case, stub_adapter
    from harness.pair_llm_stub import cooperative_model
    model = model or cooperative_model()
    cal = synthetic_cal(tmp_path, f'cal-{name or condition}')
    bundle = contract.bundle(condition, calibration=cal, synthetic_calibration=True, source_sha='0' * 40)
    out = Path(tmp_path) / (name or condition)
    result = run_pair_case(
        bundle, out, condition=condition, seed=911, backend_factory=backend, calibration=cal['path'],
        calibration_sha=cal['sha256'], provider_factory=plumbing.blind_provider_factory, cap_s=cap_s,
        runtime_factory=runtime_factory,
        adapter_factory=None if condition == 'rule' else (lambda o: stub_adapter(model, o / 'llm' / 'ledger')))
    return result, out, model


class FakeRuntime:
    """A deterministic runtime with the ``Runtime`` interface (rule-arm parity test only)."""

    def __init__(self, static, calibration, calibration_sha, *, seed, provider_factory=None):
        self.closed, self.commands, self.seen = False, [], 0

    def initial_commands(self, now, commands):
        self.initial = copy.deepcopy(commands)

    def on_frames(self, now, frames):
        assert set(frames) == set(c.ROBOTS)
        self.seen += 1

    def step(self, now):
        n = round(now * 20)
        out = []
        if n % 3 == 0:
            out.append(('r1', {'kind': 'hold'}))
        if n % 5 == 0:
            out.append(('r2', {'kind': 'drive', 'forward': n % 7, 'turn': 0}))
        return out

    def arm_step(self, now):
        return [('r2', {'kind': 'servo', 'pulses': {'1': 1500 + round(now * 20) % 9}})] if round(now * 20) % 4 == 0 else []

    def on_command(self, rid, now, action):
        self.commands.append((rid, round(now, 6), copy.deepcopy(action)))

    def record(self):
        return {'pair': []}

    def close(self):
        self.closed = True
