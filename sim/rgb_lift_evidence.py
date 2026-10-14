"""Shared command-conditioned wrist-RGB evidence, extracted from crate v2.

Sources: crate 422cc0ad (v2), b033e5f9 (v3 local-part/body comparison).
Only normalized colour-mask geometry and issued commands enter this module.
These provisional thresholds express a visual hypothesis, not measured height.
"""
from __future__ import annotations
import numpy as np

MIN_PART = .01
AREA_RATIO = (.70, 1.40)
CENTER_SHIFT = .06
EXTENT_SHIFT = .10
SETTLE_S = 3.


def shape(mask):
    """Normalized image geometry; no camera calibration or world coordinates."""
    y, x = np.nonzero(mask)
    if not len(x):
        return None
    h, w = mask.shape
    return {'fraction': float(mask.mean()), 'center': [float(x.mean()/w), float(y.mean()/h)],
            'extent': [float((x.max()-x.min()+1)/w), float((y.max()-y.min()+1)/h)]}


def lift_commands(commands):
    """Check only issued PWM/time, never measured joints or execution."""
    if len(commands) < 2:
        return {'valid': False, 'reason': 'missing issued lift history'}
    times = [c['t'] for c in commands]
    pwms = [{int(s): v for s, v in c['pwm'].items()} for c in commands]
    delta = max(max(p[s] for p in pwms)-min(p[s] for p in pwms) for s in (3, 4, 5))
    valid = (all(b >= a for a, b in zip(times, times[1:])) and times[-1]-times[0] >= 1.2-1e-8
             and delta >= 20 and all(p[1] <= 1600 for p in pwms)
             and all(p[6] == pwms[0][6] for p in pwms)
             and all(not any(c['wheels']) for c in commands))
    return {'valid': valid, 'duration_s': times[-1]-times[0], 'arm_pwm_span': delta,
            'reason': 'closed stationary issued lift' if valid else 'incomplete or incompatible issued lift'}


def confirm_parts_v2(before, after, *, commands, masks, names, settled=None, rule):
    """Compare each named colour part through issued lift and settled hold.

    Caller supplies only a colour mask function and part names. Missing evidence
    stays undetermined; no background, pose, contact or joint reading is used.
    """
    out = {'rule': rule, 'thresholds': 'provisional; uncalibrated',
           'command_evidence': lift_commands(commands), 'comparisons': []}
    if not out['command_evidence']['valid']:
        return {**out, 'verdict': 'undetermined', 'reason': out['command_evidence']['reason']}
    if before.shape != after.shape or (settled is not None and before.shape != settled.shape):
        return {**out, 'verdict': 'undetermined', 'reason': 'incompatible frame sizes'}
    reference = [shape(m) for m in masks(before)]
    if len(reference) != len(names) or not names:
        raise ValueError('one colour mask required for each named part')
    out['before'] = dict(zip(names, reference))
    if any(s is None or s['fraction'] < MIN_PART for s in reference):
        return {**out, 'verdict': 'undetermined', 'reason': 'required colour parts not visible before lift'}
    for tag, frame in [('lift_complete', after), ('settled_hold', settled)]:
        if frame is None:
            return {**out, 'verdict': 'undetermined', 'reason': 'settled hold frame missing'}
        parts = [shape(m) for m in masks(frame)]
        if len(parts) != len(names):
            raise ValueError('one colour mask required for each named part')
        comparison = {'sample': tag, 'parts': {}}
        out['comparisons'].append(comparison)
        for name, b, a in zip(names, reference, parts):
            if a is None or a['fraction'] < MIN_PART or a['fraction']/b['fraction'] < .4:
                return {**out, 'verdict': 'not_confirmed', 'reason': f'{name} disappeared or shrank (possible grip loss)'}
            ratio = a['fraction']/b['fraction']
            shift = max(abs(x-y) for x, y in zip(a['center'], b['center']))
            extent = max(abs(x-y) for x, y in zip(a['extent'], b['extent']))
            comparison['parts'][name] = {'after': a, 'area_ratio': ratio, 'center_shift': shift, 'extent_shift': extent}
            if not (AREA_RATIO[0] <= ratio <= AREA_RATIO[1] and shift <= CENTER_SHIFT and extent <= EXTENT_SHIFT):
                return {**out, 'verdict': 'undetermined', 'reason': f'{name} did not remain rigid in wrist view'}
    return {**out, 'verdict': 'confirmed', 'reason': 'colour parts co-move through issued lift and settled hold'}


def confirm_parts_v3(before, after, *, commands, masks, names, settled=None, rule,
                     relative_to=None):
    """Generalize crate b033e5f9 confirm_v3 without relaxing its thresholds.

    Each part is rigid unless ``relative_to`` names its rigid anchor. Such a
    body must persist without downward drift relative to the anchor. Solo
    cargo has no separately coloured lug, so its visible colour is the rigid
    part. Missing pixels cannot be replaced by background or issued commands.
    Record both samples, including zero masks, before deciding the verdict.
    """
    relative_to = dict(relative_to or {})
    if (not names or len(set(names)) != len(names) or
            any(body not in names or anchor not in names or anchor in relative_to
                for body, anchor in relative_to.items())):
        raise ValueError('unique parts and a rigid anchor required')
    out = {'rule': rule, 'thresholds': 'provisional; uncalibrated',
           'command_evidence': lift_commands(commands), 'comparisons': []}
    if before.shape != after.shape or (settled is not None and before.shape != settled.shape):
        return {**out, 'verdict': 'undetermined', 'reason': 'incompatible frame sizes'}

    def shapes(frame):
        values = [shape(m) for m in masks(frame)]
        if len(values) != len(names):
            raise ValueError('one colour mask required for each named part')
        return dict(zip(names, values))

    reference = shapes(before)
    out['before'] = reference
    pixels = before.shape[0]*before.shape[1]
    out['before_pixels'] = {name: round(s['fraction']*pixels) if s else 0
                            for name, s in reference.items()}
    for tag, frame in [('lift_complete', after), ('settled_hold', settled)]:
        comparison = {'sample': tag, 'missing': frame is None, 'parts': {}}
        out['comparisons'].append(comparison)
        if frame is None:
            continue
        comparison['identical_to_before'] = bool(np.array_equal(before, frame))
        parts = shapes(frame)
        for name in names:
            b, a = reference[name], parts[name]
            row = {'after': a, 'after_pixels': round(a['fraction']*pixels) if a else 0,
                   'area_ratio': 0. if b is not None and a is None else None,
                   'center_shift': None, 'extent_shift': None}
            comparison['parts'][name] = row
            if b is not None and a is not None:
                row.update(area_ratio=a['fraction']/b['fraction'],
                           center_shift=max(abs(x-y) for x, y in zip(a['center'], b['center'])),
                           extent_shift=max(abs(x-y) for x, y in zip(a['extent'], b['extent'])))
            if name in relative_to:
                anchor = relative_to[name]
                rb, ra = reference[anchor], parts[anchor]
                row['downward_relative_to_anchor'] = (
                    (a['center'][1]-ra['center'][1]) - (b['center'][1]-rb['center'][1])
                    if all(v is not None for v in (a, b, ra, rb)) else None)

    if not out['command_evidence']['valid']:
        return {**out, 'verdict': 'undetermined', 'reason': out['command_evidence']['reason']}
    if any(s is None or s['fraction'] < MIN_PART for s in reference.values()):
        return {**out, 'verdict': 'undetermined', 'reason': 'required colour parts not visible before lift'}
    for comparison in out['comparisons']:
        if comparison['missing']:
            return {**out, 'verdict': 'undetermined', 'reason': 'settled hold frame missing'}
        if comparison['identical_to_before']:
            return {**out, 'verdict': 'undetermined',
                    'reason': f"{comparison['sample']} identical to pre-lift frame; no new visual evidence"}
        for name, row in comparison['parts'].items():
            a = row['after']
            if a is None or a['fraction'] < MIN_PART or row['area_ratio'] < .4:
                return {**out, 'verdict': 'not_confirmed',
                        'reason': f'{name} disappeared or shrank (possible grip loss)'}
            if name in relative_to:
                downward = row['downward_relative_to_anchor']
                if downward is None:
                    return {**out, 'verdict': 'undetermined', 'reason': 'rigid anchor not visible'}
                if downward > CENTER_SHIFT:
                    return {**out, 'verdict': 'not_confirmed',
                            'reason': f'{name} moved down relative to {relative_to[name]}'}
            elif not (AREA_RATIO[0] <= row['area_ratio'] <= AREA_RATIO[1] and
                      row['center_shift'] <= CENTER_SHIFT and row['extent_shift'] <= EXTENT_SHIFT):
                return {**out, 'verdict': 'undetermined',
                        'reason': f'{name} did not remain rigid in wrist view'}
    return {**out, 'verdict': 'confirmed',
            'reason': 'rigid parts co-move; bodies persist without downward relative drift'}
