"""Own-RGB lift confirmation for the crate teachers (``crate_rgb_lift_v1``; uncalibrated).

Uses only the robot's own wrist-camera frames: one taken at its own lift permit and one after its
own lift command sequence completed. The held lug and the crate body move rigidly with the camera;
the floor does not. After a real lift the held pixels persist (rigid) while the floor pixels change
(camera went up). Verdict states:
- ``confirmed``     held pixels persist and the background changed,
- ``not_confirmed`` held pixels vanished (grip lost), the held object shifted in the gripper (lug/body split
  of the held pixels changed), or the background did not change (arm did not rise),
- ``undetermined``  fewer than MIN_BACKGROUND of the frame is background in either frame.
No simulator state, no contact, no height. The thresholds are provisional (not calibrated against
frames of a successful lift). The crate runner uses confirmation to authorize release and stops
on unknown/unconfirmed; agreement with evaluation-only hold truth remains unverified (확인 안 됨).
"""
from __future__ import annotations
import numpy as np

MIN_BACKGROUND = .08
PERSIST_RATIO = .6
SHIFT_LIMIT = .3          # change of the own-lug share of the held pixels that still counts as rigid
BLACK = 30                # sum of channels below this is the lens border / shadow, not floor
BACKGROUND_CHANGE = 6.     # mean absolute grey-level change of the background pixels (0-255)


def masks(rgb, end):
    """Boolean masks of (own lug colour, crate body pink) for a uint8 HxWx3 frame."""
    f = rgb.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    blue = (b > 140) & (r < 90) & (g < 90)
    teal = (g > 140) & (b > 60) & (b < g) & (r < 90)
    lug = teal if end == 'teal' else blue
    pink = (r > 90) & (r > g+25) & (b > g-5) & (r > b) & ~lug
    return lug, pink


def features(rgb, end):
    lug, pink = masks(rgb, end)
    held = lug | pink
    return {'own_lug_fraction': float(lug.mean()), 'pink_fraction': float(pink.mean()),
            'held_fraction': float(held.mean()), 'background_fraction': float(1.-held.mean())}


def confirm(before, after, end):
    """``before``/``after``: uint8 HxWx3 own frames. Returns the provisional verdict dict."""
    fb, fa = features(before, end), features(after, end)
    lug_b, pink_b = masks(before, end)
    lug_a, pink_a = masks(after, end)
    dark = (before.astype(np.int16).sum(-1) < BLACK) | (after.astype(np.int16).sum(-1) < BLACK)
    bg = ~(lug_b | pink_b) & ~(lug_a | pink_a) & ~dark
    out = {'before': fb, 'after': fa, 'rule': 'crate_rgb_lift_v1 (provisional thresholds, uncalibrated)'}
    if fb['held_fraction'] < .02:
        out.update(verdict='undetermined', reason='no held pixels before the lift')
        return out
    persist = fa['held_fraction']/fb['held_fraction']
    out['held_persistence'] = persist
    if persist < PERSIST_RATIO and fa['held_fraction'] < fb['held_fraction']*PERSIST_RATIO:
        out.update(verdict='not_confirmed', reason='held pixels vanished (grip lost)')
        return out
    shift = abs(fa['own_lug_fraction']-fb['own_lug_fraction'])/max(fb['held_fraction'], .05)
    out['held_split_shift'] = shift
    if shift > SHIFT_LIMIT:
        out.update(verdict='not_confirmed', reason='held object shifted in the gripper')
        return out
    if bg.mean() < MIN_BACKGROUND:
        out.update(verdict='undetermined', reason='background not visible in both frames', background_common=float(bg.mean()))
        return out
    change = float(np.abs(before.astype(np.int16)[bg]-after.astype(np.int16)[bg]).mean())
    out['background_change'] = change
    out['background_common'] = float(bg.mean())
    out.update(verdict='confirmed' if change >= BACKGROUND_CHANGE else 'not_confirmed',
               reason='background changed' if change >= BACKGROUND_CHANGE else 'background did not change (arm did not rise)')
    return out


# v2 is an opt-in, command-conditioned visual hypothesis, not a height sensor.
# A stalled actuator + perfectly rigid close view can be visually ambiguous.
V2_MIN_PART = .01
V2_AREA_RATIO = (.70, 1.40)
V2_CENTER_SHIFT = .06
V2_EXTENT_SHIFT = .10


def shape(mask):
    """Normalized image geometry; no camera calibration or world coordinates."""
    y, x = np.nonzero(mask)
    if not len(x):
        return None
    h, w = mask.shape
    return {'fraction': float(mask.mean()), 'center': [float(x.mean()/w), float(y.mean()/h)],
            'extent': [float((x.max()-x.min()+1)/w), float((y.max()-y.min()+1)/h)]}


def lift_commands(commands):
    """Check only issued PWM/time, never measured joints or simulated execution."""
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


def confirm_v2(before, after, end, *, commands, settled=None):
    """Own lug AND pink body stay with the wrist through lift and settled hold.

    No background is required. Area, centroid and extent must persist for each
    part independently (a pink wall/other lug cannot replace the assigned lug).
    Missing/occluded evidence remains undetermined; clear loss is not_confirmed.
    No probing pan is issued: the documented held-pan slip risk still applies.
    """
    out = {'rule': 'crate_rgb_lift_v2', 'thresholds': 'provisional; GCP validation pending',
           'command_evidence': lift_commands(commands), 'comparisons': []}
    if end not in ('blue', 'teal'):
        raise ValueError('assigned lug must be blue or teal')
    if not out['command_evidence']['valid']:
        return {**out, 'verdict': 'undetermined', 'reason': out['command_evidence']['reason']}
    if before.shape != after.shape or (settled is not None and before.shape != settled.shape):
        return {**out, 'verdict': 'undetermined', 'reason': 'incompatible frame sizes'}
    reference = [shape(m) for m in masks(before, end)]
    out['before'] = dict(zip(('lug', 'pink'), reference))
    if any(s is None or s['fraction'] < V2_MIN_PART for s in reference):
        return {**out, 'verdict': 'undetermined', 'reason': 'assigned lug and pink body not both visible before lift'}
    for tag, frame in [('lift_complete', after), ('settled_hold', settled)]:
        if frame is None:
            return {**out, 'verdict': 'undetermined', 'reason': 'settled hold frame missing'}
        parts = [shape(m) for m in masks(frame, end)]
        comparison = {'sample': tag, 'parts': {}}
        out['comparisons'].append(comparison)
        for name, b, a in zip(('lug', 'pink'), reference, parts):
            if a is None or a['fraction'] < V2_MIN_PART or a['fraction']/b['fraction'] < .4:
                return {**out, 'verdict': 'not_confirmed', 'reason': f'{name} disappeared or shrank (possible grip loss)'}
            ratio = a['fraction']/b['fraction']
            shift = max(abs(x-y) for x, y in zip(a['center'], b['center']))
            extent = max(abs(x-y) for x, y in zip(a['extent'], b['extent']))
            comparison['parts'][name] = {'after': a, 'area_ratio': ratio, 'center_shift': shift, 'extent_shift': extent}
            if not (V2_AREA_RATIO[0] <= ratio <= V2_AREA_RATIO[1] and shift <= V2_CENTER_SHIFT
                    and extent <= V2_EXTENT_SHIFT):
                return {**out, 'verdict': 'undetermined', 'reason': f'{name} did not remain rigid in wrist view'}
    return {**out, 'verdict': 'confirmed', 'reason': 'assigned lug and pink body co-move through issued lift and settled hold'}


def confirm_v3(before, after, end, *, commands, settled=None):
    """Track the grasped lug; require body retention, not a rigid silhouette.

    The two-robot crate can rotate about its lug. Keep the v2 rigidity test on
    the assigned lug, but test the body for disappearance and downward image
    drift relative to that lug. This is a visual hypothesis, not load/height
    measurement. See the crate4 reference/adaptation record. v2 is unchanged.
    """
    if end not in ('blue', 'teal'):
        raise ValueError('assigned lug must be blue or teal')
    out = {'rule': 'crate_rgb_lift_v3', 'thresholds': 'provisional; uncalibrated',
           'command_evidence': lift_commands(commands), 'comparisons': []}
    if not out['command_evidence']['valid']:
        return {**out, 'verdict': 'undetermined', 'reason': out['command_evidence']['reason']}
    if before.shape != after.shape or (settled is not None and before.shape != settled.shape):
        return {**out, 'verdict': 'undetermined', 'reason': 'incompatible frame sizes'}
    reference = [shape(m) for m in masks(before, end)]
    out['before'] = dict(zip(('lug', 'pink'), reference))
    if any(s is None or s['fraction'] < V2_MIN_PART for s in reference):
        return {**out, 'verdict': 'undetermined', 'reason': 'assigned lug and pink body not both visible before lift'}
    for tag, frame in [('lift_complete', after), ('settled_hold', settled)]:
        if frame is None:
            return {**out, 'verdict': 'undetermined', 'reason': 'settled hold frame missing'}
        parts = [shape(m) for m in masks(frame, end)]
        comparison = {'sample': tag, 'parts': {}}
        out['comparisons'].append(comparison)
        for name, b, a in zip(('lug', 'pink'), reference, parts):
            if a is None or a['fraction'] < V2_MIN_PART or a['fraction']/b['fraction'] < .4:
                return {**out, 'verdict': 'not_confirmed', 'reason': f'{name} disappeared or shrank (possible grip loss)'}
            ratio = a['fraction']/b['fraction']
            shift = max(abs(x-y) for x, y in zip(a['center'], b['center']))
            extent = max(abs(x-y) for x, y in zip(a['extent'], b['extent']))
            row = {'after': a, 'area_ratio': ratio, 'center_shift': shift, 'extent_shift': extent}
            comparison['parts'][name] = row
            if name == 'lug':
                if not (V2_AREA_RATIO[0] <= ratio <= V2_AREA_RATIO[1] and
                        shift <= V2_CENTER_SHIFT and extent <= V2_EXTENT_SHIFT):
                    return {**out, 'verdict': 'undetermined', 'reason': 'lug did not remain rigid in wrist view'}
            else:
                downward = ((a['center'][1]-parts[0]['center'][1]) -
                            (b['center'][1]-reference[0]['center'][1]))
                row['downward_relative_to_lug'] = downward
                if downward > V2_CENTER_SHIFT:
                    return {**out, 'verdict': 'not_confirmed', 'reason': 'pink moved down relative to held lug'}
    return {**out, 'verdict': 'confirmed',
            'reason': 'assigned lug co-moves; pink persists without downward relative drift'}


class LiftObserver:
    """Small runner adapter: capture before own permit, after own completion, at 3s.

    Dependencies are a capture callback and the robot's own issued command only.
    The callback can save the frames and hashes without changing the classifier.
    """
    def __init__(self, end, *, mode='crate_rgb_lift_v2'):
        if mode not in ('crate_rgb_lift_v2', 'crate_rgb_lift_v3'):
            raise ValueError('unknown crate lift observer mode')
        self.confirm = confirm_v3 if mode == 'crate_rgb_lift_v3' else confirm_v2
        self.end = end
        self.before = self.after = None
        self.commands = []
        self.completed_at = None
        self.verdict = None

    def observe(self, *, permit, complete, command, capture):
        if self.before is None:
            if not permit:
                return None
            self.before = capture('before_lift')
        if self.verdict is not None:
            return self.verdict
        self.commands.append(command)
        if complete and self.after is None:
            self.after = capture('lift_complete')
            self.completed_at = command['t']
        if self.after is not None and command['t']-self.completed_at >= 3.-1e-8:
            self.verdict = self.confirm(self.before, self.after, self.end, commands=self.commands,
                                       settled=capture('settled_hold'))
        return self.verdict
