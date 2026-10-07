"""Single frozen M/N development replay, both conditions. No unseen admission here."""
import argparse,subprocess,os
from monitor_common import *
from gate import summary
from harness.public_navigation_monitor import build


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--navigation',choices=['off','public_ros_v8'],default='off')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.navigation=='off':p.error('explicit public_ros_v8 required; default off')
    frozen=read(EXP/'freeze.json');current=hashes()
    assert current==frozen['hashes'] and SETTINGS==frozen['settings'] and CRITERIA==frozen['criteria']
    assert sha(v7.RAW/'confirmation/results.json')==frozen['development_prior_results_sha256']
    manifest=read(v7.EXP/'cohort.json')
    assert sha(v7.EXP/'cohort.json')==frozen['development_cohort_sha256']
    native=build()
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,criteria=CRITERIA,cohort=manifest,split='development',
        pose_condition='oracle_gt_pose_v1',native_sha256=sha(native),load_average=os.getloadavg(),
        physics=0,model_calls=0,wall_time_benchmark=False))
    runner=configure(manifest);results=[]
    for entry in manifest['rows']:
        for mode in ('static_map','own_frontier'):
            i,start,seed=(entry[k] for k in ('scenario','start','seed'))
            name=f's{i}-{start}-{seed}-{mode}'
            # Keep original world seed/draw condition "confirmation". The evidence
            # split is development; re-labelling must not secretly redraw data.
            result=episode(runner,i,start,seed,'confirmation',mode,'oracle',args.output/name)
            result['split']='development'
            write(args.output/name/'result.json',result)
            results.append(result);write(args.output/'results.json',results)
            print(name,result['status'],'coverage',round(result['coverage'],4),'contacts',result['collisions'],
                  'false_passage',result['false_candidate_passage_attempts'],flush=True)
    assert hashes()==current and 'mujoco' not in sys.modules
    decision=summary(results,True)
    decision['split']='development'
    decision['next_stage']='REGISTER_NEW_COHORT' if decision['passed'] else 'STOP_NO_TUNING'
    write(args.output/'gate.json',decision)
    print('GATE',decision['checks'],decision['passed'],flush=True)

if __name__=='__main__':main()
