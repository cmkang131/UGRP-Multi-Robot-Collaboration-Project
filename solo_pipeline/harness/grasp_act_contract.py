"""Serializable student capability: own images, issued commands and task only.

No simulator, teacher, measured joints, object pose, or evaluation imports.
The skill/end token is an instruction, not an estimated/privileged pose.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

SCHEMA = 'ugrp.grasp_act.student.v6'
SKILLS = ('grasp', 'wait', 'regrasp', 'release')
KINDS = ('cyan', 'green', 'red', 'yellow', 'can', 'tile', 'long_beam', 'heavy_crate', 'tri_frame')
ROLES = ('teal', 'blue', 'west', 'east', 'any', 'v0', 'v1', 'v2')
KIND_ROLES = {**{k: ('west',) for k in ('cyan', 'green', 'red', 'yellow')},
              'can': ('any',), 'tile': ('west', 'east'), 'long_beam': ('teal', 'blue'),
              'heavy_crate': ('west', 'east'), 'tri_frame': ('v0', 'v1', 'v2')}
DESTINATIONS = ('none','A','B','C','pickup_site')
SERVOS = (1, 3, 4, 5, 6)
MEMORY_S = 5.2  # v2 final blind motion minus GT-only verification; recheck v3 gate
HISTORY = 16
RGB_LAGS_S = (5.2, 1.5, .5, 0.)
RGB_HISTORY = len(RGB_LAGS_S)
CHUNK = 8
PERIOD_S = .1
ACTION_DIM = 14  # four wheels, four pulse widths, five PWM targets, command completion
CONTEXT_DIM = HISTORY * 14 + len(SKILLS) + len(KINDS) + len(ROLES) + len(DESTINATIONS) + 2
FIELDS = {'schema', 'robot_id', 'sample_id', 't', 'skill', 'object_kind', 'role', 'rgb', 'issued', 'skill_elapsed_s', 'pwm_elapsed_s', 'destination_zone'}
COMMAND_FIELDS = {'t', 'wheels', 'duration_s', 'pwm'}


def wheel_mix(drive):
    f, l, t = drive
    return (f-l-t, f+l+t, f+l-t, f-l+t)


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('finite numeric value required')
    return float(value)


def command(row):
    if not isinstance(row, Mapping) or set(row) != COMMAND_FIELDS:
        raise ValueError('issued-command whitelist mismatch')
    t = finite(row['t'])
    wheels = [finite(v) for v in row['wheels']]
    duration = [finite(v) for v in row['duration_s']]
    if len(wheels) != 4 or len(duration) != 4:
        raise ValueError('four wheel commands and pulse widths required')
    for w, dt in zip(wheels, duration):
        if not (w == 0. or .31-1e-9 <= abs(w) <= .40+1e-9):
            raise ValueError('wheel range is zero or 31..40 percent')
        if not 0. <= dt <= .15 or ((w == 0.) != (dt == 0.)):
            raise ValueError('each moving wheel needs a pulse within 150 ms')
    pwm = row['pwm']
    if not isinstance(pwm, Mapping) or set(pwm) != {str(s) for s in SERVOS}:
        raise ValueError('exact own issued PWM channels required')
    for v in pwm.values():
        if type(v) is not int or not 500 <= v <= 2500:
            raise ValueError('invalid issued PWM')
    return {'t': t, 'wheels': wheels, 'duration_s': duration, 'pwm': dict(pwm)}


def validate_observation(row):
    if not isinstance(row, Mapping) or set(row) != FIELDS or row['schema'] != SCHEMA:
        raise ValueError('student observation whitelist mismatch')
    if row['robot_id'] not in ('r1', 'r2', 'r3') or not isinstance(row['sample_id'], str):
        raise ValueError('unknown actor')
    t = finite(row['t'])
    if row['skill'] not in SKILLS or row['object_kind'] not in KIND_ROLES or row['role'] not in KIND_ROLES[row['object_kind']]:
        raise ValueError('task instruction must be a skill and named end')
    if row['destination_zone'] not in DESTINATIONS or (row['skill']=='release' and row['destination_zone']=='none'):
        raise ValueError('release requires a named destination zone')
    if len(row['rgb']) != RGB_HISTORY or len(row['issued']) != HISTORY:
        raise ValueError('fixed own image and command history required')
    for key in ('skill_elapsed_s', 'pwm_elapsed_s'):
        if finite(row[key]) < 0.: raise ValueError('nonnegative issued-command clock required')
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
    if times!=sorted(times) or times[-1]>t or t-times[-1]>.15 or t-times[0]>MEMORY_S+.15:
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
        values.extend(x['wheels'])
        values.extend(d/.15 for d in x['duration_s'])
        values.extend((x['pwm'][str(s)]-1500)/1000 for s in SERVOS)
        values.append(min(MEMORY_S, row['t']-x['t'])/MEMORY_S)
    values.extend(float(row['skill'] == s) for s in SKILLS)
    values.extend(float(row['object_kind'] == s) for s in KINDS)
    values.extend(float(row['role'] == s) for s in ROLES)
    values.extend(float(row['destination_zone']==s) for s in DESTINATIONS)
    values.extend(min(120., row[k])/120. for k in ('skill_elapsed_s', 'pwm_elapsed_s'))
    assert len(values) == CONTEXT_DIM
    return values


def image_history(refs, now):
    """Time-only subsampling; never choose frames using truth or teacher labels."""
    if not refs:raise ValueError('nonempty own image buffer required')
    from bisect import bisect_right
    times=[r['t'] for r in refs]
    return [refs[max(0,bisect_right(times,now-lag+1e-7)-1)] for lag in RGB_LAGS_S]


class IssuedClock:
    """Only instruction changes and issued PWM changes update these clocks."""
    def __init__(self):
        self.skill = None; self.started = None; self.changed = None; self.pwm = None
    def observe(self, instruction, now, issued_pwm):
        now = finite(now)
        if instruction != self.skill or self.started is None:
            self.skill = instruction; self.started = now
        if self.pwm != issued_pwm or self.changed is None:
            self.pwm = dict(issued_pwm); self.changed = now
        return {'skill_elapsed_s': now-self.started, 'pwm_elapsed_s': now-self.changed}


def encode_action(issued, *, done=False):
    x = command(issued)
    return x['wheels'] + [d/.15 for d in x['duration_s']] + [
        (x['pwm'][str(s)]-1500)/1000 for s in SERVOS] + [float(done)]


def decode_action(values):
    """Project each real wheel into its allowed range; no measured-state correction."""
    if len(values) != ACTION_DIM: raise ValueError('wrong ACT output size')
    v = [finite(x) for x in values]; done = v[-1] >= .65
    wheels=[];duration=[]
    for w,d in zip(v[:4],v[4:8]):
        dt=max(0.,min(.15,d*.15))
        if done or abs(w)<.155 or dt<.001: wheels.append(0.);duration.append(0.)
        else: wheels.append(math.copysign(max(.31,min(.40,abs(w))),w));duration.append(dt)
    pwm = {str(s): round(max(500,min(2500,1500+1000*v[i+8]))) for i,s in enumerate(SERVOS)}
    return {'wheels':wheels,'duration_s':duration,'pwm':pwm,'done':done,
            'done_score':max(0.,min(1.,v[-1]))}


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
        if (label['sample_id'] != obs['sample_id'] or label['skill'] != obs['skill']
                or label['object_kind'] != obs['object_kind'] or type(label['done']) is not bool):
            raise ValueError('misaligned teacher target')
        if label['done'] and label['terminal_reason'] != 'command_sequence_complete':
            raise ValueError('only successful skill completion is a done target')
        action, pad = [], []
        ended = False
        for k in range(chunk):
            j = i+k
            valid = not ended and j < len(labels) and abs(observations[j]['t']-obs['t']-k*PERIOD_S)<1e-5 and (observations[j]['skill'], observations[j]['object_kind'], observations[j]['role'], observations[j]['destination_zone']) == (obs['skill'], obs['object_kind'], obs['role'], obs['destination_zone'])
            if valid:
                y = labels[j]
                action.append(encode_action(y['clean_teacher_command'], done=y['done']))
                ended = bool(y['done'])
            else:
                action.append([0.] * ACTION_DIM)
            pad.append(not valid)
        result.append({'sample_id': obs['sample_id'], 'action': action, 'action_is_pad': pad})
    return result
