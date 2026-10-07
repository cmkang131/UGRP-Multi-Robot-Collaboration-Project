"""One preregistered oracle, paired static efficiency denominator; default off."""
import argparse
import subprocess
from unknown_common import *
import register_new
from gate import summary
from harness.public_navigation_unknown import build


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--navigation',choices=['off','public_ros_v7'],default='off')
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    if args.navigation=='off':p.error('Explicit public_ros_v7 required; default off')
    frozen = read(EXP/'freeze.json')
    current = hashes()
    assert current==frozen['hashes'] and SETTINGS==frozen['settings'] and CRITERIA==frozen['criteria']
    assert sha(RAW/'development/results.json')==frozen['development_results_sha256']
    dev = read(RAW/'development/results.json')
    assert len(dev)==32 and all(r['after']['robot_component_cells']>36 and r['after']['valid']>=1 for r in dev)
    manifest = read(EXP/'cohort.json')
    assert manifest==register_new.generate() and sha(EXP/'cohort.json')==frozen['cohort_sha256']
    prior = v6.prior.verify_prior()
    args.output.mkdir(parents=True,exist_ok=False)
    native = build()
    write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,criteria=CRITERIA,cohort_sha256=sha(EXP/'cohort.json'),prior_gate=prior,
        pose_condition='oracle_gt_pose_v1',stage='b',cohort='confirmation',physics=0,model_calls=0,
        native_sha256=sha(native),python=sys.version,load_average=__import__('os').getloadavg()))
    runner = configure(manifest)
    results = []
    for entry in manifest['rows']:
        for mode in ('static_map','own_frontier'):
            i,start,seed = (entry[k] for k in ('scenario','start','seed'))
            name = f's{i}-{start}-{seed}-{mode}'
            result = runner.episode(i,start,seed,'confirmation',mode,'oracle',args.output/name)
            results.append(result)
            write(args.output/'results.json',results)
            print(name,result['status'],'coverage',round(result['coverage'],4),'collisions',result['collisions'],flush=True)
    assert hashes()==current and 'mujoco' not in sys.modules
    decision = summary(results,True)
    write(args.output/'gate.json',decision)
    print('GATE',decision['checks'],decision['passed'],flush=True)


if __name__=='__main__':main()
