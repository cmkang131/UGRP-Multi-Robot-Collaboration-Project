"""Fixed v149 RGB/issued-command replay; no GT/evaluation-file access."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.zone_s3_motion_runtime import Runtime
from harness.pulse_rotation_odometry import OPTION


def replay(raw,out,mode):
    path=Path(__file__).parents[1]/'s3fix2/profile_replay.py'
    spec=importlib.util.spec_from_file_location('s3_saved_own_replay',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    def runtime(*a,**kw):
        config=copy.deepcopy(kw.pop('config'))
        if mode!='off':config['options']['pulse_odometry']=mode
        return Runtime(*a,config=config,**kw)
    bind(old.replay,Runtime=runtime)(raw,out,False,measure=False)
    report=json.loads((out/'result.json').read_text()); report['pulse_odometry']=mode
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['off',OPTION],required=True);a=p.parse_args()
    replay(a.raw,a.output,a.mode)
