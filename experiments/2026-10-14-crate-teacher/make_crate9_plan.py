"""Same diagnostic proposal/LOS distribution, static kinematics only."""
import json
from pathlib import Path
import mujoco
from scripts.make_crate_teacher_plan import prepare
from scripts.audit_crate_start_los import CrateStartLOS

def forbidden(*args, **kwargs):
    raise AssertionError('crate9 forbids physics, forward and rendering on Mac')

def main():
    for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_inverse','Renderer','mjr_render'):
        setattr(mujoco,name,forbidden)
    original=CrateStartLOS.check
    def check(self,episode,**kwargs):
        episode['cargo_scene_version']='crate_mass_025_v1'
        return original(self,episode,**kwargs)
    CrateStartLOS.check=check
    plan=prepare(count=10,seed=77970,split='crate_diagnostic',scenario_set='v5',
                 start_assigned_los='start_assigned_los_v1')
    plan['criteria']['denominators']='diagnostic N=10 including failures and HOST_ERROR; no gate authorized'
    out=Path(__file__).with_name('diag_plan_crate9_77970.json')
    out.write_text(json.dumps(plan,separators=(',',':'))+'\n')
    print(json.dumps({'episodes':len(plan['episodes']),'accepted':plan['start_los_audit']['accepted'],
                      'physics_steps':0,'render_calls':0}))
if __name__=='__main__':main()
