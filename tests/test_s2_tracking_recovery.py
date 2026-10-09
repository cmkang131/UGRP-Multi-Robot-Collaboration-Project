import copy
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import zone_solo_cyan_tracking_recovery as m
from test_s2_augmented_start import particle_filter


def test_default_and_explicit_off_are_object_and_byte_identical():
    obj=NS(record=lambda:dict(actions=[{'forward':.35}],seed=1060))
    before=dict(obj.__dict__);raw=json.dumps(obj.record()).encode()
    assert m.attach(obj) is obj and m.attach(obj,localization_recovery='off') is obj
    assert obj.__dict__==before and json.dumps(obj.record()).encode()==raw


def test_nav2_ema_arithmetic_and_flat_low_likelihood_still_injects():
    p=m.Policy();pf=particle_filter(2000);pf.t=10.
    for score in (20.,20.,.02):
        prior=pf._weights();slow,fast=p.slow,p.fast
        q=p.measure(pf,prior,np.log(np.full(pf.n,score)),{},True)
        avg=score/2000
        slow=avg if slow==0 else slow+.001*(avg-slow)
        fast=avg if fast==0 else fast+.1*(avg-fast)
        assert q['w_avg']==pytest.approx(avg)
        assert q['w_slow']==pytest.approx(slow) and q['w_fast']==pytest.approx(fast)
        assert q['injection_probability']==pytest.approx(max(0,1-fast/slow))
        assert q['resampled'] and q['samples_before']==q['samples_after']==2000
    assert q['ess']==pytest.approx(2000) and q['injected']>0
    assert np.count_nonzero(pf.px[:,0]==-99)==q['injected']
    assert p.slow==p.fast==0
    assert not p.new_view({6:970})


def test_handoff_preserves_initial_policy_and_attaches_only_once():
    global_policy=NS(active=True);pf=NS(s2_global_policy=global_policy)
    runtime=NS(start_prior='none_v1',global_localization='augmented_active_v1',particle_sampling='kld_global_v1',
        global_policy=global_policy,amcl_audit={},record=lambda:{'old':'same'},
        pose=NS(provider=NS(loc=NS(_pf=pf),runtime_contract={})))
    def command(rid,t,action):
        if action.get('forward') and global_policy.active:
            global_policy.active=False;del pf.s2_global_policy
        return 'old'
    runtime.on_command=command;m.attach(runtime,localization_recovery=m.OPTION)
    assert runtime.on_command('r3',1.,{'kind':'hold'})=='old' and pf.s2_global_policy is global_policy
    runtime.on_command('r3',10.5,{'kind':'mecanum','forward':.35})
    policy=pf.s2_global_policy;policy.slow=3.
    runtime.on_command('r3',11.,{'kind':'hold'})
    assert pf.s2_global_policy is policy and policy.slow==3.
    assert runtime.record()['localization_recovery']['attached_t']==10.5
    assert runtime.record()['old']=='same'
    with pytest.raises(ValueError,match='ALREADY'):m.attach(runtime,localization_recovery=m.OPTION)


def test_reject_invalid_or_unsupported_stack():
    for value in ('bad',m.OPTION):
        with pytest.raises(ValueError):m.attach(NS(),localization_recovery=value)


def test_preregistered_parameters_are_not_tuned():
    from pathlib import Path
    c=json.loads(Path('experiments/2026-10-06-s2-realism/tracking-recovery-criteria.json').read_text())
    assert c['parameters']==dict(alpha_slow=.001,alpha_fast=.1,resample_interval=1,tracking_particles=2000)
    assert c['recovery_xy_m']==.25 and c['convergence_std_xy_m']==.05
