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
GIVEUP_S = 120.
VERSIONS = {'e2e18-v301': 302}
PARAMS = dict(giveup_after_relook_s=GIVEUP_S, correction_applied=False, dev_light_only=True,
              route_after_relook_called=False,
              source='own_execution_phase_timer_only')


def compose(bundle, option):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    if option != OPTION or parent not in VERSIONS:
        raise ValueError('RELOOK_GIVEUP_REQUIRES_V301')
    version = VERSIONS[parent]
    bundle['relook_giveup_parent'] = parent
    bundle['e2e_options']['relook_giveup'] = option
    bundle['relook_giveup_parameters'] = copy.deepcopy(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)


def parent_for_validation(bundle):
    parent = bundle.get('relook_giveup_parent')
    if (parent not in VERSIONS or bundle['execution_bundle_id'] != f'e2e18-v{VERSIONS[parent]}'
            or bundle['e2e_options'].get('relook_giveup') != OPTION
            or bundle.get('relook_giveup_parameters') != PARAMS):
        raise ValueError('REGISTERED_RELOOK_GIVEUP_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = parent
    old['e2e_options'].pop('relook_giveup')
    old.pop('relook_giveup_parent')
    old.pop('relook_giveup_parameters')
    return old


def giveup(tr, now):
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
    if option == 'off':
        return tr
    original = tr.step

    def stepped(now):
        out = original(now)
        if (tr.state == 'relook' and tr.dev_light and not tr.failure
                and now - tr.stage_t > GIVEUP_S):
            out = out + giveup(tr, now)
        return out
    tr.step = stepped
    return tr
