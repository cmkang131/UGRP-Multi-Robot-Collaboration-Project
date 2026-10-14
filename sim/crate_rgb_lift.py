"""Own-RGB lift confirmation for the crate teachers (``crate_rgb_lift_v1``; record-only, uncalibrated).

Uses only the robot's own wrist-camera frames: one taken at its own lift permit and one after its
own lift command sequence completed. The held lug and the crate body move rigidly with the camera;
the floor does not. After a real lift the held pixels persist (rigid) while the floor pixels change
(camera went up). Verdict states:
- ``confirmed``     held pixels persist and the background changed,
- ``not_confirmed`` held pixels vanished (grip lost), the held object shifted in the gripper (lug/body split
  of the held pixels changed), or the background did not change (arm did not rise),
- ``undetermined``  fewer than MIN_BACKGROUND of the frame is background in either frame.
No simulator state, no contact, no height. The thresholds are provisional (not calibrated against
frames of a successful lift); the runner stores the verdict next to the evaluation-only lift truth so
the agreement can be counted before this verdict is allowed to gate anything (확인 안 됨).
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
    """``before``/``after``: uint8 HxWx3 own frames. Returns the verdict dict (record only)."""
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
