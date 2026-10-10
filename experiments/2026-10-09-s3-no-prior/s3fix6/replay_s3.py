"""Fixed archived own RGB/issued commands; selected optional PF consumer."""
import argparse,copy,importlib.util,json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.zone_s3_consistent_runtime import Runtime
from harness.pf_observation_consistency import OPTIONS

def replay(raw,out,option):
    source=Path(__file__).parents[1]/'s3fix5/recover_smoke.py'
    spec=importlib.util.spec_from_file_location('s3fix6_original_replay',source)
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    def factory(*a,config,**kw):
        selected=copy.deepcopy(config)
        selected['options'].update(observation_consistency=option,pose_validity='defer_unmeasured_v1')
        return Runtime(*a,config=selected,**kw)
    bind(previous.replay,Runtime=factory)(raw,out,False,measure=False)
    p=out/'result.json';r=json.loads(p.read_text());r.update(observation_consistency=option,pose_validity='defer_unmeasured_v1');p.write_text(json.dumps(r,indent=2)+'\n')
    if r['error']:raise RuntimeError(r['error'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--option',choices=OPTIONS,default='off');a=p.parse_args()
    replay(a.raw,a.output,a.option)
