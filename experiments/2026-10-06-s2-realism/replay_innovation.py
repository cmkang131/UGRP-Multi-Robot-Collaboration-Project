"""Frozen commands/RGB only. Evaluation code is a separate entry point."""
import argparse,importlib.util,json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import attach as bias,SCALE,TEMPER
from harness.zone_solo_cyan_approach_vo import attach,OPTION
from scripts.audit_s2_formal_stops import OUTPUTS,read
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_replay',HERE/'replay_rotation_left.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True)
    p.add_argument('--condition',choices=['baseline','candidate'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--max-frames',type=int);a=p.parse_args()
    table=read(OUTPUTS/'s2-bias-tempering-v45-20261008/fit'/f's{a.seed}-calibration.json')
    assert table['holdout']==a.seed and a.seed not in table['fit_seeds'];holder={}
    def selected(runtime,**_):
        runtime=bias(runtime,forward_scale=SCALE,likelihood_tempering=TEMPER,
            calibration=table,servo_stiffness='real_v1',audit=True)
        runtime=attach(runtime,ground_motion=OPTION if a.condition=='candidate' else 'off',servo_stiffness='real_v1')
        holder['runtime']=runtime
        return runtime
    replay=bind(old.replay,attach=selected,CRITERIA=HERE/'innovation-criteria.json')
    replay(a.seed,a.condition,a.output,a.max_frames)
    now=read(a.output/f's{a.seed}-{a.condition}.json')
    if a.condition=='baseline':
        previous=read(OUTPUTS/'s2-bias-tempering-v45-20261008/replay'/f's{a.seed}-combined.json')
        assert json.dumps(now['poses']).encode()==json.dumps(previous['poses'][:len(now['poses'])]).encode()
        if not a.max_frames:assert now['particle_trajectory_sha256']==previous['particle_trajectory_sha256']
    audit=dict(measurements=holder['runtime'].measurement_consistency_audit)
    with (a.output/f's{a.seed}-{a.condition}-measurement.json').open('x') as f:json.dump(audit,f);f.write('\n')

if __name__=='__main__':main()
