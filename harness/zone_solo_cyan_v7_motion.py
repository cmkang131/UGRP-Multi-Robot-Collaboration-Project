"""Frozen v7 diagnostic coefficients, opt-in only; all prediction uses own commands."""
from harness.zone_solo_cyan_real_output import Runtime as Base
from harness import zone_pair_highpose_contract as hp


class Runtime(Base):
    def __init__(self,*args,dead_reckoning='off',motion_model=None,**kwargs):
        super().__init__(*args,dead_reckoning=dead_reckoning,motion_model=motion_model,**kwargs)
        if dead_reckoning=='v7_diag_v1':
            inner=self.pose.provider;pf=inner.loc._pf
            for key in ('motion','motion_loaded'):
                pf.params[key]['tau_axis_s']=list(motion_model['tau_axis_s'])
            inner.runtime_contract['v7_motion_option']=motion_model
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_v7_diag:'+inner.identity_sha256[:8]
            self.pose.source=inner.source
