"""Mode-switch chatter guard for visual_servo <-> clip_recovery (default off).

Diagnosis (e2e18 v302 r59 r1, 318 s on): the visual servo drives forward (+0.35), the
band is clipped, clip_recovery drives back (-0.35), the end flickers visible, the
servo goes forward again: a 0.8 s limit cycle for ~200 SIM s. clip_recovery also
dropped its 3-pulse budget on every single `end_visible` frame, so the budget never ran out.

Rule (own RGB frames and own issued commands only; no truth, contact or joints):
- entry debounce: a pulse needs `enter_frames` consecutive clipped frames;
- exit hysteresis: after a pulse the visual-servo handoff is held until the end has been
  visible for `exit_frames` consecutive frames AND `min_dwell_s` has passed since the
  pulse (released after `max_hold_s` regardless, recorded; DEV-light never stops);
- budget: the pulse budget is reset only after `reset_frames` consecutive end-visible
  frames (a lone flicker no longer resets it).

Standard references (not re-verified against the originals, recalled from memory):
hysteresis / minimum dwell / debounce against mode chattering in hybrid or behaviour
switching controllers (Liberzon, "Switching in Systems and Control", 2003; Nav2
behaviour-tree recovery with bounded retries); field-of-view keeping in IBVS
(Chaumette & Hutchinson, IEEE RAM 2006). The numbers are ours.
"""
import copy

OPTIONS = ('v1',)
PARAMS = dict(enter_frames=2, exit_frames=3, reset_frames=6, min_dwell_s=1.6, max_hold_s=12.,
              own_rgb_and_commands_only=True)
VERSIONS = {'e2e18-v310': 312, 'e2e18-v303': 313}


def compose(bundle, option):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    if option not in OPTIONS or parent not in VERSIONS:
        raise ValueError('CLIP_HYSTERESIS_REQUIRES_V310_OR_V303')
    version = VERSIONS[parent]
    bundle['clip_hysteresis_parent'] = parent
    bundle['e2e_options']['clip_hysteresis'] = option
    bundle['clip_hysteresis_parameters'] = copy.deepcopy(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)


def parent_for_validation(bundle):
    parent = bundle.get('clip_hysteresis_parent')
    if (parent not in VERSIONS or bundle['execution_bundle_id'] != f'e2e18-v{VERSIONS[parent]}'
            or bundle['e2e_options'].get('clip_hysteresis') not in OPTIONS
            or bundle.get('clip_hysteresis_parameters') != PARAMS):
        raise ValueError('REGISTERED_CLIP_HYSTERESIS_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = parent
    old['e2e_options'].pop('clip_hysteresis')
    old.pop('clip_hysteresis_parent')
    old.pop('clip_hysteresis_parameters')
    return old


def install(tr, option='off'):
    tr.clip_hysteresis = option
    return tr


def enabled(tr):
    return getattr(tr, 'clip_hysteresis', 'off') != 'off'


def _st(state):
    return state.setdefault('clip_hyst', dict(frame=None, visible_run=0, clipped_run=0, hold_t=None))


def _fresh(st, obs):
    key = obs['rgb'].get('frame_id', obs['rgb']['t_sim'])
    if key == st['frame']:
        return False
    st['frame'] = key
    return True


def end_visible_seen(tr, rid, now, state, obs, attempt):
    """Count end-visible frames; return True when the pulse budget may be reset."""
    st = _st(state)
    if _fresh(st, obs):
        st['visible_run'] += 1
        st['clipped_run'] = 0
    if st['hold_t'] is not None and st['visible_run'] >= PARAMS['exit_frames'] \
            and now-st['hold_t'] >= PARAMS['min_dwell_s']:
        st['hold_t'] = None
    return attempt is not None and st['visible_run'] >= PARAMS['reset_frames']


def clipped_seen(tr, rid, now, state, obs):
    """Count consecutive clipped frames; True once the entry debounce is met."""
    st = _st(state)
    if _fresh(st, obs):
        st['clipped_run'] += 1
        st['visible_run'] = 0
    return st['clipped_run'] >= PARAMS['enter_frames']


def pulsed(state, now):
    _st(state)['hold_t'] = now


def blocked(tr, rid, now, state):
    """True while the visual-servo handoff must wait for a stable end-visible view."""
    if not enabled(tr):
        return False
    st = state.get('clip_hyst')
    if not st or st['hold_t'] is None:
        return False
    if now-st['hold_t'] > PARAMS['max_hold_s']:
        tr.event(now, 'clip_hysteresis_released', robot_id=rid, held_s=now-st['hold_t'], dev_light=tr.dev_light)
        st['hold_t'] = None
        return False
    return True
