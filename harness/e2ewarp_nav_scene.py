"""Nav-gate scene-profile selection (2026-10-21 BRANCH_NAV_V5; default OFF).

Why this exists: the D4 scene-fit test (``experiments/2026-10-21-act18-scene-fit``,
frozen prereg ``SCENE_FIT_PREREG.json`` sha256 ``9c2b5ba2...``, commits
``7aa8c3d87`` / ``1bb49dcda``) evaluated the ACT C2c grasp on the nav v6 scene
(neutral pickup tiles) and measured G 1/4 (Pre 2 / done 3 / lift 1 / release 0 /
cap_end 2).  The pre-registered branch for G <= 1/4 is ``BRANCH_NAV_V5``: keep
ACT on its training scene ``walls_floor_contrast_v5_indigo110_s80`` and
re-calibrate navigation there instead.

This module only *selects* the scene profile for the nav gate.  It never imports
a simulator.  Selection is an explicit opt-in environment variable; with the
variable unset the queue, stack values and scene XML stay byte-identical to the
v230_r5 gate (current stack ``walls_floor_contrast_v6_indigo110_s80_neutral_start``).

- ``E2EWARP_NAV_SCENE_PROFILE`` unset / ``stack``: no change (default).
- ``E2EWARP_NAV_SCENE_PROFILE=v5``: nav uses ``walls_floor_contrast_v5_indigo110_s80``.
  The substitution is written into the queue as a stack deviation plus two
  explicit markers, and ``validate_scene_queue`` re-checks the binding before any
  physics import (fail closed both ways: env without markers, markers without env).

Results on v5 and v6 are separate conditions and are never pooled.
"""
from __future__ import annotations

import os

SCENE_ENV = 'E2EWARP_NAV_SCENE_PROFILE'
SELECTION_STACK = 'stack'
SELECTION_V5 = 'v5'
V5_PROFILE = 'walls_floor_contrast_v5_indigo110_s80'
V6_PROFILE = 'walls_floor_contrast_v6_indigo110_s80_neutral_start'
SELECTIONS = {SELECTION_STACK: None, SELECTION_V5: V5_PROFILE}
DEFAULT_SELECTION = SELECTION_STACK
APPROVAL = dict(
    # check_current_stack accepts only user/coordinator authority.  The branch
    # was pre-registered and routed by the coordinator (2026-10-21); a direct
    # user approval quote is not recorded here ([확인 필요]).
    authority='coordinator',
    evidence=('pre-registered branch, 2026-10-21 D4 scene fit (experiments/2026-10-21-act18-scene-fit, '
              'SCENE_FIT_PREREG.json FROZEN sha256 9c2b5ba220e314a34f80d369dadbb2e01d1f793c'
              '987772f2d25a32fff30b5bab, commits 7aa8c3d87/1bb49dcda): ACT C2c on v6 '
              'G 1/4 <= 1/4 -> BRANCH_NAV_V5 (nav re-calibrated on the ACT v5 scene)'))


def scene_selection(name=None):
    """Return ``{'name', 'profile'}``; ``profile`` is ``None`` when OFF."""
    raw = name if name is not None else os.environ.get(SCENE_ENV, DEFAULT_SELECTION)
    raw = str(raw).strip() or DEFAULT_SELECTION
    if raw not in SELECTIONS:
        raise ValueError('NAV_SCENE_PROFILE_UNKNOWN:' + raw)
    return dict(name=raw, profile=SELECTIONS[raw])


def apply_scene_profile(values, selection=None):
    """Return ``(values, deviation)``; OFF returns the same object and ``None``.

    The v5 selection replaces only ``scene_profile``.  It requires the current
    stack value to be the v6 nav profile so a silently changed stack cannot be
    relabelled as the v5 branch.
    """
    sel = selection or scene_selection()
    if sel['profile'] is None:
        return values, None
    current = values.get('scene_profile')
    if current != V6_PROFILE:
        raise ValueError('NAV_SCENE_STACK_PROFILE_UNEXPECTED:' + str(current))
    out = dict(values)
    out['scene_profile'] = sel['profile']
    deviation = dict(id='scene_profile', reason=(
        'BRANCH_NAV_V5: nav gate on the ACT training scene; stack value '
        + V6_PROFILE + ' -> ' + sel['profile'] + ' (visual-only, changes_physics False)'),
        stack_current=V6_PROFILE, applied=sel['profile'], approval=dict(APPROVAL))
    return out, deviation


def scene_queue_fields(selection=None):
    """Explicit opt-in markers; OFF adds nothing (queue bytes unchanged)."""
    sel = selection or scene_selection()
    if sel['profile'] is None:
        return {}
    return dict(nav_scene_profile_selection=sel['name'], nav_scene_profile=sel['profile'])


def validate_scene_queue(queue, selection=None):
    """Re-check env <-> queue <-> stack_values binding before physics import."""
    sel = selection or scene_selection()
    marker = queue.get('nav_scene_profile_selection')
    profile = queue.get('nav_scene_profile')
    applied = (queue.get('stack_values') or {}).get('scene_profile')
    deviations = [d for d in queue.get('stack_deviations') or () if d.get('id') == 'scene_profile']
    if sel['profile'] is None:
        if marker is not None or profile is not None:
            raise ValueError('NAV_SCENE_PROFILE_MARKER_WITHOUT_ENV')
        if applied == V5_PROFILE or deviations:
            raise ValueError('NAV_SCENE_PROFILE_V5_WITHOUT_ENV')
        return queue
    if marker != sel['name'] or profile != sel['profile']:
        raise ValueError('NAV_SCENE_PROFILE_MARKER_MISMATCH')
    if applied != sel['profile']:
        raise ValueError('NAV_SCENE_PROFILE_STACK_VALUE_MISMATCH')
    if len(deviations) != 1 or deviations[0].get('applied') != sel['profile']:
        raise ValueError('NAV_SCENE_PROFILE_DEVIATION_REQUIRED')
    return queue
