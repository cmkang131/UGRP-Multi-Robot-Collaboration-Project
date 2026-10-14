"""Serializable student capability: own images, issued commands and task only.

No simulator, teacher, measured joints, object pose, or evaluation imports.
The skill/end token is an instruction, not an estimated/privileged pose.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

SCHEMA = 'ugrp.grasp_act.student.v1'
SKILLS = ('grasp_end', 'wait', 'regrasp', 'release')
ROLES = ('teal', 'blue')
SERVOS = (1, 3, 4, 5, 6)
HISTORY = 4
CHUNK = 8
PERIOD_S = .1
ACTION_DIM = 10  # drive x/y/yaw, duration, five absolute PWM targets, skill done
CONTEXT_DIM = HISTORY * 10 + len(SKILLS) + len(ROLES)
FIELDS = {'schema', 'robot_id', 'sample_id', 't', 'skill', 'role', 'rgb', 'issued'}
COMMAND_FIELDS = {'t', 'drive', 'duration_s', 'pwm'}


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('finite numeric value required')
    return float(value)


def command(row):
    if not isinstance(row, Mapping) or set(row) != COMMAND_FIELDS:
        raise ValueError('issued-command whitelist mismatch')
    t, duration = finite(row['t']), finite(row['duration_s'])
    drive = [finite(v) for v in row['drive']]
    if len(drive) != 3 or sum(v != 0 for v in drive) > 1:
        raise ValueError('one drive axis at a time')
    if any(v != 0 and abs(v) != .35 for v in drive):
        raise ValueError('v7 primitive speed must be 35')
    if duration not in (0., .06, .15):
        raise ValueError('unknown pulse duration')
    if any(drive) != (duration > 0):
        raise ValueError('hold/pulse duration mismatch')
    if drive[1] and duration != .06:
        raise ValueError('lateral drive requires the existing 60 ms fine primitive')
    pwm = row['pwm']
    if not isinstance(pwm, Mapping) or set(pwm) != {str(s) for s in SERVOS}:
        raise ValueError('exact own issued PWM channels required')
    for v in pwm.values():
        if type(v) is not int or not 500 <= v <= 2500:
            raise ValueError('invalid issued PWM')
    return {'t': t, 'drive': drive, 'duration_s': duration, 'pwm': dict(pwm)}


def validate_observation(row):
    if not isinstance(row, Mapping) or set(row) != FIELDS or row['schema'] != SCHEMA:
        raise ValueError('student observation whitelist mismatch')
    if row['robot_id'] not in ('r1', 'r2') or not isinstance(row['sample_id'], str):
        raise ValueError('unknown actor')
    t = finite(row['t'])
    if row['skill'] not in SKILLS or row['role'] not in ROLES:
        raise ValueError('task instruction must be a skill and named end')
    if len(row['rgb']) != 2 or len(row['issued']) != HISTORY:
        raise ValueError('two own images and four own command snapshots required')
    times = []
    for ref in row['rgb']:
        if set(ref) != {'path', 'sha256', 't', 'robot_id'} or ref['robot_id'] != row['robot_id']:
            raise ValueError('own RGB reference required')
        if len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256']):
            raise ValueError('RGB SHA256 required')
        parts = ref['path'].replace('\\', '/').split('/')
        if ref['path'].startswith('/') or '..' in parts or not parts[0] == 'rgb':
            raise ValueError('RGB path must stay in episode rgb/')
        times.append(finite(ref['t']))
    if not times[0] <= times[1] <= t or t-times[1] > .6:
        raise ValueError('future, reversed or stale image')
    commands = [command(x) for x in row['issued']]
    ctimes = [x['t'] for x in commands]
    if ctimes != sorted(ctimes) or ctimes[-1] > t:
        raise ValueError('future or reversed command history')
    return row


def context(row):
    validate_observation(row)
    values = []
    for x in row['issued']:
        values.extend(v/.35 for v in x['drive'])
        values.append(x['duration_s']/.15)
        values.extend((x['pwm'][str(s)]-1500)/1000 for s in SERVOS)
        values.append(min(5., row['t']-x['t'])/5.)
    values.extend(float(row['skill'] == s) for s in SKILLS)
    values.extend(float(row['role'] == s) for s in ROLES)
    assert len(values) == CONTEXT_DIM
    return values


def encode_action(issued, *, done=False):
    x = command(issued)
    return [v/.35 for v in x['drive']] + [x['duration_s']/.15] + [
        (x['pwm'][str(s)]-1500)/1000 for s in SERVOS] + [float(done)]


def decode_action(values):
    """Bounded native primitives; no pose correction or teacher fallback."""
    if len(values) != ACTION_DIM:
        raise ValueError('wrong ACT output size')
    v = [finite(x) for x in values]
    done = v[-1] >= .65
    drive = [0., 0., 0.]
    axis = max(range(3), key=lambda i: abs(v[i]))
    if not done and abs(v[axis]) >= .5:
        drive[axis] = math.copysign(.35, v[axis])
    duration = (.06 if axis == 1 or v[3] < .7 else .15) if any(drive) else 0.
    pwm = {str(s): round(max(500, min(2500, 1500+1000*v[i+4])))
           for i, s in enumerate(SERVOS)}
    return {'drive': drive, 'duration_s': duration, 'pwm': pwm,
            'done': done, 'done_score': max(0., min(1., v[-1]))}


def training_windows(observations, labels, *, chunk=CHUNK):
    """Do not cross episode/actor/skill boundaries or turn timeout into done."""
    if len(observations) != len(labels) or not observations:
        raise ValueError('paired nonempty observations and labels required')
    result = []
    previous_t = -math.inf
    identity = (observations[0]['robot_id'], observations[0]['sample_id'].split(':')[0])
    for i, (obs, label) in enumerate(zip(observations, labels)):
        validate_observation(obs)
        if (obs['robot_id'], obs['sample_id'].split(':')[0]) != identity or obs['t'] < previous_t:
            raise ValueError('sequence crosses actor/episode or reverses time')
        previous_t = obs['t']
        if label['sample_id'] != obs['sample_id'] or label['skill'] != obs['skill']:
            raise ValueError('misaligned teacher target')
        if label['done'] and label['terminal_reason'] != 'skill_success':
            raise ValueError('only successful skill completion is a done target')
        action, pad = [], []
        ended = False
        for k in range(chunk):
            j = i+k
            valid = not ended and j < len(labels) and (observations[j]['skill'], observations[j]['role']) == (obs['skill'], obs['role'])
            if valid:
                y = labels[j]
                action.append(encode_action(y['clean_teacher_command'], done=y['done']))
                ended = bool(y['done'])
            else:
                action.append([0.] * ACTION_DIM)
            pad.append(not valid)
        result.append({'sample_id': obs['sample_id'], 'action': action, 'action_is_pad': pad})
    return result
