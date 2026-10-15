"""Static assigned-LOS/clearance audit and same-seed proposal regeneration.

MuJoCo is used only for model kinematics and first-hit rays. Step, forward,
world/reset and all rendering are forbidden; this is not a physical run.
"""
import hashlib,json,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
HERE=Path(__file__).parent

def main():
    import mujoco
    def forbidden(*a,**k):raise AssertionError('physics/render forbidden')
    for k in ('mj_step','mj_forward','Renderer'):setattr(mujoco,k,forbidden)
    from scripts.audit_crate_start_los import CrateStartLOS
    from scripts.make_crate_teacher_plan import prepare,station_clearance
    old=json.loads((HERE/'diag_plan_crate13_79314.json').read_text())
    checker=CrateStartLOS();rows=[];new=[]
    for i,e in enumerate(old['episodes']):
        report=checker.check({**e,'cargo_scene_version':'crate_mass_025_v1'})
        clear=station_clearance(e)
        rows.append({'seed':e['seed'],'los_pass':report['accepted'], 'per_robot':{r:v['gate5'] for r,v in report['robots'].items()},
                     'station_clearance_m':clear,'station_pass':min(clear.values())>=.34,
                     'accepted':report['accepted'] and min(clear.values())>=.34})
    # Regenerate the identical 10 diagnostic indices; this redraws proposals
    # from the assigned-peer distribution, never changes their recorded runs.
    # Generate all prior indices to preserve the generator's original strata.
    p=prepare(count=12,seed=79314,split='crate13_diagnostic',assignment='fixed_rgb_lugs_v1',scenario_set='v6',crate_profile='crate14_v1')
    seeds={e['seed'] for e in old['episodes']}
    new=[e for e in p['episodes'] if e['seed'] in seeds];assert len(new)==10
    packed_path=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate14-audit/regenerated-same-indices.json.zst')
    raw=(json.dumps(p,separators=(',',':'))+'\n').encode()
    packed=subprocess.check_output(['zstd','-q','-c'],input=raw)
    assert subprocess.check_output(['zstd','-q','-d','-c'],input=packed)==raw
    packed_path.write_bytes(packed)
    result={'regenerated_proposals_artifact':{'path':str(packed_path),'sha256':hashlib.sha256(packed).hexdigest(),'uncompressed_sha256':hashlib.sha256(raw).hexdigest()},'scope':'offline static rays/conditional setup proposals, no physics/render or teacher success',
      'source_plan_sha256':hashlib.sha256((HERE/'diag_plan_crate13_79314.json').read_bytes()).hexdigest(),
      'original10':{'N':10,'los_pass':sum(r['los_pass'] for r in rows),'station_rejected':sum(not r['station_pass'] for r in rows),
                    'union_rejected':sum(not r['accepted'] for r in rows),'accepted':sum(r['accepted'] for r in rows),'rows':rows},
      'regenerated_same10':{'N':10,'los_pass':sum(e['start_los_audit']['accepted'] for e in new),
                            'station_pass':sum(min(e['peer_station_clearance_m'].values())>=.34 for e in new),
                            'near_wall':sum(e['near_wall'] for e in new)},
      'regeneration_proposals_all12_indices':{k:v for k,v in p['start_distribution'].items() if k!='rejected_starts'},
      'fresh10':{},'mj_step_calls':0,'mj_forward_calls':0,'render_calls':0}
    f=json.loads((HERE/'diag_plan_crate14_79450.json').read_text())
    result['fresh10']={'seeds':[e['seed'] for e in f['episodes']], 'los_pass':sum(e['start_los_audit']['accepted'] for e in f['episodes']),
                      'start_distribution':{k:v for k,v in f['start_distribution'].items() if k!='rejected_starts'},
                      'near_wall_filter':{k:v for k,v in f['near_wall_filter'].items() if k!='excluded_episodes'}}
    out=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate14-audit/start-audit.json')
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('original10','regeneration_proposals_all12_indices')},indent=2))
if __name__=='__main__':main()
