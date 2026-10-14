"""Own-input recording; teacher targets and evaluation never enter observations.

This writer neither constructs a simulator nor selects teacher actions. Raw
JPEGs are the exact bytes captured for the controller, before the next command.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from harness.grasp_act_contract import (SCHEMA, HISTORY, MEMORY_S, PERIOD_S,
    IssuedClock, command, image_history, validate_observation)


def camera_config():
    # Read the actual student's camera configuration and command clock; never
    # confuse the ACT network's 224x224 resize with the native input stream.
    from sim import masterpi_camera_profile as c
    from sim import masterpi_camera_review_v3 as mount
    sources = ('sim/masterpi_camera_profile.py', 'sim/masterpi_camera_review_v3.py',
               'sim/s2_realism_camera_binding.py', 'harness/grasp_act_contract.py')
    root = Path(__file__).resolve().parents[1]
    return {'width': c.CAMERA_NATIVE_WIDTH, 'height': c.CAMERA_NATIVE_HEIGHT,
        'period_s': PERIOD_S, 'hz': 1/PERIOD_S, 'camera': 'robot_cam',
        'pinhole_hfov_deg': c.CAMERA_PINHOLE_HFOV_DEG,
        'pinhole_vfov_deg': c.CAMERA_PINHOLE_VFOV_DEG,
        'raw_fisheye_fov': 'nonlinear K/D; no single angular FOV',
        'K': c.scaled_camera_matrix(c.CAMERA_NATIVE_WIDTH, c.CAMERA_NATIVE_HEIGHT).tolist(),
        'fisheye_D': list(c.CAMERA_FISHEYE_D), 'mount': mount.PROFILE_ID,
        'position_m': list(mount.POSITION_M), 'quat_wxyz': list(mount.QUAT_WXYZ),
        'schema': SCHEMA, 'sources': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sources}}


def segment(phase, local_started=False):
    if phase in ('start', 'fold', 'approach', 'align', 'relook'):
        return 'approach' if local_started else 'navigation'
    if phase in ('lookback', 'lookback_return'):
        return 'carry'
    if phase in ('lower', 'open', 'retract', 'backoff'):
        return 'release'
    if phase in ('lookaround', 'complete', 'failed'):
        return 'inspection'
    return 'grasp'


def rgb_handoff(frame, pwm, kind):
    """Annotation only: 0.8 m handoff from own RGB/FK, never teacher GT."""
    from harness.zone_color_boxes import detect_own, OWN_PROFILE_ZONE
    found = detect_own(frame, pwm, kinds=(kind,), profile=OWN_PROFILE_ZONE)['detections']
    distances = [math.hypot(*x['estimated_box_center_base_m'][:2]) for x in found]
    return min(distances, default=None)


class SoloRecorder:
    def __init__(self, root, plan, initial, *, handoff=rgb_handoff):
        self.root, self.plan, self.handoff = Path(root), plan, handoff
        self.config = camera_config()
        self.images = deque(maxlen=math.ceil(MEMORY_S/PERIOD_S)+3)
        self.history = deque([deepcopy(command(initial)) for _ in range(HISTORY)], maxlen=HISTORY)
        self.clock = IssuedClock()
        self.pending = None
        self.local_started = False
        self.rows, self.rgb_bytes = 0, 0
        self.last_t = None
        (self.root/'rgb'/plan['robot_id']).mkdir(parents=True)
        self.obs_file = (self.root/f"student-{plan['robot_id']}.jsonl").open('x')
        self.label_file = (self.root/f"teacher-{plan['robot_id']}.jsonl").open('x')
        (self.root/'student-camera.json').write_text(json.dumps(self.config, indent=2)+'\n')

    def observe(self, now, jpeg, frame, *, skill, phase, previous):
        if self.pending is not None:
            raise ValueError('observation missing its aligned target')
        if self.last_t is not None and abs(now-self.last_t-PERIOD_S) > .002:
            raise ValueError('native recording period mismatch')
        if frame.shape != (self.config['height'], self.config['width'], 3):
            raise ValueError('native recording resolution mismatch')
        if previous != self.history[-1] or previous['t'] > now:
            raise ValueError('observation must precede the next issued action')
        rel = f"rgb/{self.plan['robot_id']}/{self.rows:06d}.jpg"
        (self.root/rel).write_bytes(jpeg)
        self.images.append({'path': rel, 'sha256': hashlib.sha256(jpeg).hexdigest(),
                            'robot_id': self.plan['robot_id'], 't': now})
        distance = None
        if not self.local_started and phase in ('approach', 'align'):
            distance = self.handoff(frame, previous['pwm'], self.plan['kind'])
            self.local_started = distance is not None and 0 <= distance <= .8
        row = {'schema': SCHEMA, 'robot_id': self.plan['robot_id'],
            'sample_id': f"{self.plan['episode_id']}:{self.rows}:{self.plan['robot_id']}",
            't': now, 'skill': skill, 'object_kind': self.plan['kind'], 'role': self.plan['role'],
            'destination_zone': 'pickup_site' if skill == 'release' else 'none',
            'rgb': image_history(list(self.images), now), 'issued': deepcopy(list(self.history)),
            **self.clock.observe(skill, now, previous['pwm'])}
        validate_observation(row)
        self.obs_file.write(json.dumps(row, allow_nan=False)+'\n')
        self.pending = (row, phase, distance)
        self.rgb_bytes += len(jpeg)
        self.last_t = now
        return row

    def target(self, value, *, skill_after, phase_after, complete):
        row, phase, distance = self.pending
        value = command(value)
        if value['t'] != row['t']:
            raise ValueError('teacher action / observation clock mismatch')
        done = ((row['skill'] == 'grasp' and skill_after == 'release') or
                (row['skill'] == 'release' and phase != 'complete' and complete))
        label = {'sample_id': row['sample_id'], 'skill': row['skill'], 'object_kind': row['object_kind'],
            'done': bool(done), 'terminal_reason': 'command_sequence_complete' if done else None,
            'clean_teacher_command': value, 'teacher_phase': phase, 'phase_after': phase_after,
            'segment': segment(phase, self.local_started), 'local_skill_sample': bool(self.local_started and
                phase not in ('start', 'fold', 'lookaround', 'complete', 'failed')),
            'handoff_source': 'own_rgb_and_issued_commands', 'handoff_distance_m': distance}
        self.label_file.write(json.dumps(label, allow_nan=False)+'\n')
        self.history.append(deepcopy(value))
        self.rows += 1
        self.pending = None

    def flush(self):
        self.obs_file.flush()
        self.label_file.flush()

    def close(self):
        self.obs_file.close()
        self.label_file.close()

    def record(self):
        return {'frames': self.rows, 'rgb_bytes': self.rgb_bytes, 'camera': self.config,
                'unpaired_observations': int(self.pending is not None),
                'history_bootstrap': 'repeat first issued hold/frame until history exists',
                'command_alignment': 'own RGB + previous issued history -> next teacher command at same t',
                'local_handoff_seen': self.local_started, 'raw_retained_for_failures': True}


def validate_recording(plan, *, training_rgb, truth_free_v1, negative, stability, reach, lift, margin):
    if not training_rgb:
        return
    from harness.grasp_act_seed_splits import check_range
    from sim.grasp_act_solo_teacher import BOX_KINDS
    check_range('train', plan['seed'], 1)
    if (plan.get('split') != 'train' or plan['kind'] not in BOX_KINDS or negative
            or not truth_free_v1 or stability != 'align_relook_v1' or reach != 'pad_window_v2'
            or lift != 'solo_lift_lookback_v1' or not margin):
        raise ValueError('recording requires fresh train boxes and corrected gate profile')


def validate_approval(path, *, stage, sha, host):
    """Pilot raw may be collected; bulk needs an explicit source-bound review.

    A success gate on the old, truth-assisted look-around cannot qualify this
    corrected teacher. The coordinator supplies the new gate and two inspected
    recording checks, with hashes, after actual runs; no automatic promotion.
    """
    if stage == 'pilot':
        if path is not None:
            raise ValueError('pilot has no bulk admission')
        return None
    if stage != 'batch' or path is None:
        raise ValueError('batch requires coordinator recording approval')
    proof = json.loads(Path(path).read_text())
    gate = proof.get('corrected_teacher_gate', {})
    checks = proof.get('pilot_checks', [])
    if (proof.get('approved') is not True or proof.get('source_sha') != sha
            or proof.get('gate_promotion_authorized_if_all_conditions_pass') is not False
            or gate.get('source_sha') != sha or gate.get('solo_truth_free_lookaround_v1') is not True
            or gate.get('N', 0) < 40 or gate.get('n', 0)/max(1, gate.get('N', 0)) < .95
            or len(checks) != 2 or any(c.get('passed') is not True or not c.get('path')
                or not isinstance(c.get('sha256'), str) or len(c['sha256']) != 64
                or any(ch not in '0123456789abcdef' for ch in c['sha256']) for c in checks)
            or len({c.get('path') for c in checks}) != 2):
        raise ValueError('uncorrected gate / missing inspected pilots / source mismatch')
    from scripts.grasp_act_host import same_machine
    same_machine(gate.get('execution_host'), host)
    return proof
