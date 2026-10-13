"""DEV-light dead-reckoning continuation after an unmatched set-down relook (default off).

AGENTS.md "dev_light": a missed re-observation deadline is only recorded
("would stop here") and the run continues. The existing relook branch records
one `would_stop` and then waits forever, because `OwnRGBRelook.pending` keeps
hijacking localization. This toggle ends that wait after a bounded number of
SIM seconds: it clears the pending relook (no correction is minted or faked),
resets the dialogue/route state the same way the success branch does and returns
to mapping with the uncorrected own pose, i.e. the legacy no-relook flow.
Only own execution state is read; the result is a DEV diagnostic, not a
self-localization success.
"""
import copy

OPTION = 'dev_light_v1'
OPTION_REST = 'dev_light_rest_v1'   # + beam-at-rest drop-guard (evaluation only)
GIVEUP_S = 120.
VERSIONS = {('e2e18-v301', OPTION): 302, ('e2e18-v280', OPTION): 303,
            ('e2e18-v280', OPTION_REST): 304, ('e2e18-v301', OPTION_REST): 305}
PARAMS = dict(giveup_after_relook_s=GIVEUP_S, correction_applied=False, dev_light_only=True,
              route_after_relook_called=False,
              source='own_execution_phase_timer_only')


def compose(bundle, option):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    if (parent, option) not in VERSIONS:
        raise ValueError('RELOOK_GIVEUP_REQUIRES_V301_OR_V280')
    version = VERSIONS[(parent, option)]
    if option == OPTION_REST:
        bundle['drop_guard_rest_parameters'] = dict(rest_s=1.0, max_com_z_m=.03, max_abs_vz_m_s=.02,
                                                     evaluation_only=True)
    bundle['relook_giveup_parent'] = parent
    bundle['e2e_options']['relook_giveup'] = option
    bundle['relook_giveup_parameters'] = copy.deepcopy(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json', 'sim/s4_beam_drop_guard.py')


def parent_for_validation(bundle):
    parent = bundle.get('relook_giveup_parent')
    option = bundle['e2e_options'].get('relook_giveup')
    if ((parent, option) not in VERSIONS or bundle['execution_bundle_id'] != f'e2e18-v{VERSIONS[(parent, option)]}'
            or bundle.get('relook_giveup_parameters') != PARAMS
            or (option == OPTION_REST) != ('drop_guard_rest_parameters' in bundle)
            or (option == OPTION_REST and bundle['drop_guard_rest_parameters'] != dict(
                rest_s=1.0, max_com_z_m=.03, max_abs_vz_m_s=.02, evaluation_only=True))):
        raise ValueError('REGISTERED_RELOOK_GIVEUP_REQUIRED')
    old = copy.deepcopy(bundle)
    if option == OPTION_REST:
        old.pop('drop_guard_rest_parameters')
    old['execution_bundle_id'] = parent
    old['e2e_options'].pop('relook_giveup')
    old.pop('relook_giveup_parent')
    old.pop('relook_giveup_parameters')
    return old


def giveup(tr, now):
    if getattr(tr,'post_relook_handler',None) and not getattr(tr,'_post_relook_dispatching',False):
        return tr.post_relook_handler(tr,now)
    waited = now - tr.stage_t
    pending = {}
    for rid in ('r1', 'r2'):
        rl = tr.robots[rid].goal.e2e_relook
        pending[rid] = None if rl.pending is None else dict(node=rl.pending.get('node'), matches=len(rl.pending.get('matches', [])))
        rl.emit(dict(event='e2e_relook_giveup', t=now, seg=tr.seg, epoch=tr.epoch,
                     correction_applied=False, waited_s=waited))
        rl.pending = None
        rl.receipt = None
    tr.event(now, 'would_stop', reason='OWN_RGB_METRIC_CORRECTION_TIMEOUT', state=tr.state,
             dev_light=True, relook_giveup=True)
    tr.event(now, 'e2e_relook_giveup', waited_s=waited, pending=pending, seg=tr.seg,
             correction_applied=False, parameters=copy.deepcopy(PARAMS))
    tr.robots['r1'].packet = None
    d = tr.dialogue
    d.approved = False; d.proposal = None; d.claims = set(); d.key = None; d.votes = {}
    tr.aligned = {}; tr.approach = {}; tr.seg = 0; tr.first_seg = 0; tr.plan = None
    tr.set('mapping', now)
    return [(rid, dict(kind='hold')) for rid in ('r1', 'r2')]


def install(tr, option='off'):
    tr.relook_giveup = option
    if option == OPTION_REST:
        import sim.s4_beam_drop_guard as guard
        guard.REST_CLEAR_DEFAULT = True      # evaluation-only; the bundle records drop_guard_rest_parameters
    if option == 'off':
        return tr
    original = tr.step

    def stepped(now):
        out = original(now)
        if (tr.state == 'relook' and tr.dev_light and not tr.failure
                and now - tr.stage_t > getattr(tr,'post_relook_wait_s',GIVEUP_S)):
            out = out + giveup(tr, now)
        return out
    tr.step = stepped
    return tr
