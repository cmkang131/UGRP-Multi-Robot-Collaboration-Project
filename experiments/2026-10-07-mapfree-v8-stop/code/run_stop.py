"""One old M/N32 development cohort; no unopened/noisy admission before 5/5."""
import argparse,os,subprocess
from stop_common import *
from gate import summary
from integer_episode import episode
from harness.public_navigation_monitor import build


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--navigation',choices=['off','public_ros_v8'],default='off')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.navigation=='off':p.error('explicit public_ros_v8 required; default off')
    frozen=read(EXP/'freeze.json')
    current=hashes()
    assert current==frozen['hashes'] and SETTINGS==frozen['settings'] and CRITERIA==frozen['criteria']
    assert sha(PRIOR/'results.json')==frozen['prior_results_sha256']
    manifest=read(v8.v7.EXP/'cohort.json')
    assert sha(v8.v7.EXP/'cohort.json')==frozen['development_cohort_sha256']
    native=build()
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,criteria=CRITERIA,cohort=manifest,split='development',
        pose_condition='oracle_gt_pose_v1',native_sha256=sha(native),load_average=os.getloadavg(),
        physics=0,model_calls=0,wall_time_benchmark=False))
    runner=configure(manifest)
    results=[]
    for entry in manifest['rows']:
        for mode in ('static_map','own_frontier'):
            i,start,seed=(entry[k] for k in ('scenario','start','seed'))
            name=f's{i}-{start}-{seed}-{mode}'
            # Original world draw split is unchanged, evidence role is development.
            result=episode(runner,i,start,seed,'confirmation',mode,'oracle',args.output/name)
            result['split']='development'
            write(args.output/name/'result.json',result)
            waits=read(args.output/name/'eval_wait_checks.json')
            assert all(w['distance_m']==0. and w['max_abs_model_velocity']==0. and
                w['new_contacts']==0 and w['pose_delta']==[0.,0.,0.] for w in waits)
            results.append(result)
            write(args.output/'results.json',results)
            print(name,result['status'],'coverage',round(result['coverage'],4),
                'contacts',result['collisions'],'false_passage',result['false_candidate_passage_attempts'],flush=True)
    assert hashes()==current and 'mujoco' not in sys.modules
    decision=summary(results,True)
    decision.update(split='development',next_stage='REGISTER_NEW_COHORT' if decision['passed'] else 'STOP_TRACK_FINAL',
        observation_wait_stop_verified=True)
    write(args.output/'gate.json',decision)
    print('GATE',decision['checks'],decision['passed'],flush=True)


if __name__=='__main__':main()
