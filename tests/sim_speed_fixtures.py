"""Small complete M1 evidence fixtures, independent of physics and active slots."""
import hashlib
import json
from pathlib import Path

LOGS = ('inputs/commands.jsonl', 'inputs/frames.jsonl', 'controller_events.jsonl', 'skill_events.jsonl',
        'macros.jsonl', 'eval_only/frames_eval.jsonl', 'eval_only/gt_trajectory.jsonl',
        'eval_only/contacts.jsonl', 'eval_only/retention.jsonl')
RECORDING_START_SIM_S = 1.3003  # dev-a8 s93/s95: sampling begins after scene setup


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def refresh_manifest(run):
    path = run/'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files'] = {name: hashlib.sha256((run/name).read_bytes()).hexdigest()
                         for name in LOGS if (run/name).is_file()}
    path.write_text(json.dumps(manifest))


def full_run(root):
    root = Path(root)
    start = RECORDING_START_SIM_S
    times = [round(start + .2*i, 4) for i in range(6)]
    phases = ['grasp', 'grasp', 'to_carry_posture', 'nav_preplace', 'release', 'look_back']
    frames = []
    for i, (t, phase) in enumerate(zip(times, phases)):
        name = f'frames/{i:05d}.jpg'
        (root/name).parent.mkdir(parents=True, exist_ok=True)
        raw = f'fixture jpeg {i}'.encode()
        (root/name).write_bytes(raw)
        frames.append({'frame': i, 't': t, 'file': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                       'phase': 'skill', 'skill_phase': phase})
    eval_frames = [{k: r[k] for k in ('frame', 't', 'phase', 'skill_phase')} | {'box_xyz': [0, 0, .05]}
                   for r in frames]
    commands = [{'t': 0., 'kind': 'initial_servo_command', 'pulses': {}},
                {'t': start + .25, 'kind': 'wait'}, {'t': start + .5, 'kind': 'hold'}]
    rows = {
        LOGS[0]: commands, LOGS[1]: frames,
        'controller_events.jsonl': [{'t': start + .01, 'event': 'skill_start', 'phase': 'skill'},
                                   {'t': start + 1., 'event': 'look_back_gate', 'phase': 'skill'}],
        'skill_events.jsonl': [{'event': 'grasp_attached', 'phase': 'grasp'},
                              {'event': 'carry_posture_anchored', 'phase': 'to_carry_posture'}],
        'macros.jsonl': [{'t': start + .05, 'skill_phase': 'grasp', 'action': {'kind': 'wait'}},
                        {'t': start + .4, 'skill_phase': 'to_carry_posture', 'action': {'kind': 'pose'}},
                        {'t': start + .8, 'skill_phase': 'release', 'action': {'kind': 'pose'}}],
        'eval_only/frames_eval.jsonl': eval_frames,
        'eval_only/gt_trajectory.jsonl': [{'t': round(start + .05*i, 4), 'box_xyz': [0, 0, .05]}
                                        for i in range(20)],
        'eval_only/contacts.jsonl': [],
        'eval_only/retention.jsonl': [{'t': round(start + .4 + .05*i, 4),
                                     'phase': 'to_carry_posture' if i < 4 else 'nav_preplace',
                                     'steps': 200, 'both_finger_steps': 200, 'min_box_z_m': .05}
                                    for i in range(8)]}
    for name, values in rows.items(): write_rows(root/name, values)
    result = {'schema': 'ugrp.m1_owncam_run.v3', 'outcome': 'IN_SLOT', 'sim_s': round(start + 1., 2),
              'frames': len(frames), 'commands': len(commands),
              'phase_times': {'skill:grasp': round(start, 2), 'skill:to_carry_posture': round(start + .4, 2),
                              'skill:nav_preplace': round(start + .6, 2), 'skill:release': round(start + .8, 2),
                              'skill:look_back': round(start + 1., 2)},
              'evaluation_only': {'contacts': {'wall': 0, 'peer_robot': 0, 'other_box': 0},
                                  'retention': {'carry_steps': 1600, 'both_finger_steps': 1600}}}
    (root/'result.json').write_text(json.dumps(result))
    (root/'manifest.json').write_text(json.dumps({'schema': result['schema'], 'timestep_s': .00025,
        'frame_period_s': .2, 'tick_s': .1, 'files': {}, 'wall_s': 1.0, 'code': {'sha': 'fixture'}}))
    refresh_manifest(root)
    return root


def full_profile(root):
    full_run(root/'run')
    (root/'run'/'attempt_started.json').write_text('{}')
    rows = [{'step': i, 't': i*.00025, 'sha256': str(i//4600)*64} for i in (4600, 9200)]
    write_rows(root/'qpos_checkpoints.jsonl', rows)
    meta = {'qpos_every': 4600, 'mj_steps': 9200, 'checkpoints': 2,
            'initial_sim_s': 0., 'timestep': .00025, 'final_checkpoint': rows[-1],
            'last_step_checkpoint': rows[-1]}
    (root/'profile.json').write_text(json.dumps(meta))
    return root
