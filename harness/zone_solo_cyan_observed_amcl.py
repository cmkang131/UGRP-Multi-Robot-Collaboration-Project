"""Default-off S2 measured-beam preprocessing before the Nav2 field model.

No particle-prior visibility veto. Standard likelihood and odometry trigger
stay in zone_solo_cyan_amcl_update. Only observed own-body/cyan pixels are
missing measurements; RGB missing returns are never fabricated max ranges.
"""
import copy
import numpy as np
from harness.zone_solo_cyan_amcl_update import Runtime as Previous

OPTION='nav2_observed_v1'


def install(visibility):
    audit=visibility.audit
    audit.update(policy=OPTION,prior_visibility_veto=False,
                 preprocessing='observed pixel ray/body and own RGB cyan only')
    audit['parameters']=dict(robot_padding_m=audit['parameters']['robot_padding_m'],
        cargo_padding_px=audit['parameters']['cargo_padding_px'],min_columns=1,
        prior_visible_probability=None)

    def apply(pf,obs,pose,t):
        # Camera lookup is own commanded posture + immutable calibration.
        # Deliberately never access pf.px, expected(), weights(), or covariance.
        cm=pf.column_model_for(pose);cols=np.arange(len(obs.columns))
        valid=(obs.b_kind==1)&np.isfinite(obs.b_lo)&(obs.b_lo>=0)&(obs.b_lo<480)
        rows=np.rint(np.nan_to_num(obs.b_lo)).astype(int).clip(0,479)
        trace=cm.t_of_row(obs.b_lo);depth=cm.alpha[:,2]+trace*cm.beta[:,2]
        self_depth=visibility.depth_image(cm,pose)[rows,cols]
        self_shadow=valid&(self_depth<=depth)
        cargo_shadow=np.zeros(len(cols),bool)
        if visibility.cargo is not None:
            cargo_shadow=valid&visibility.cargo[rows,obs.columns.astype(int)]
        keep=valid&~self_shadow&~cargo_shadow
        masked=copy.deepcopy(obs);masked.b_kind[~keep]=0;masked.t_kind[:]=0
        audit['rows'].append(dict(t=float(t),detected=int((obs.b_kind==1).sum()),
            kept=int(keep.sum()),prior_view_columns=None,prior_visibility_veto=False,
            detected_self_shadow=int(self_shadow.sum()),detected_cargo_shadow=int(cargo_shadow.sum())))
        return masked if keep.any() else None

    visibility.apply=apply


class Runtime(Previous):
    def __init__(self,*args,visibility_policy='off',**kwargs):
        if visibility_policy not in ('off',OPTION):raise ValueError('unknown visibility_policy')
        if visibility_policy!='off' and (kwargs.get('amcl_update')!='ros_motion_v1' or
                kwargs.get('visibility_mask')!='command_geometry_v1'):
            raise ValueError('observed policy requires fixed Nav2 field and explicit own geometry mask')
        self.visibility_policy=visibility_policy
        super().__init__(*args,**kwargs)
        if visibility_policy!='off':
            install(self.visibility)
            inner=self.pose.provider
            inner.runtime_contract['s2_visibility_policy']=dict(option=OPTION,prior_visibility_veto=False,
                observation_inputs='own RGB and commands plus fixed geometry/calibration',gt_inputs=False)
            from harness.zone_solo_cyan_v106 import hp
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_observed_amcl:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def record(self):
        out=super().record()
        if self.visibility_policy!='off':out['visibility_policy']=dict(option=OPTION,
            prior_visibility_veto=False,measurement='Nav2 default hit/random cubic field unchanged',gt_inputs=False)
        return out
