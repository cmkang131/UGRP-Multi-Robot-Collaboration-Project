"""Frozen own-RGB replay, new options and noninvasive measurement audit."""
import argparse,importlib.util,json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import attach,SCALE,TEMPER
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('old_replay',HERE/'replay_rotation_left.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('--condition',choices=['off','scale','temper','combined'],required=True)
    p.add_argument('--calibration',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-frames',type=int);a=p.parse_args()
    table=json.loads(a.calibration.read_text()) if a.calibration else None
    if a.condition in ('scale','combined'):assert table['holdout']==a.seed and a.seed not in table['fit_seeds']
    holder={}
    def selected(runtime,**_):
        holder['runtime']=attach(runtime,forward_scale=SCALE if a.condition in ('scale','combined') else 'off',
            likelihood_tempering=TEMPER if a.condition in ('temper','combined') else 'off',calibration=table,servo_stiffness='real_v1',audit=True)
        return holder['runtime']
    replay=bind(old.replay,attach=selected,CRITERIA=HERE/'bias-tempering-criteria.json')
    replay(a.seed,a.condition,a.output,a.max_frames)
    runtime=holder['runtime'];audit=dict(option=runtime.bias_tempering_audit,measurements=runtime.measurement_consistency_audit)
    with (a.output/f's{a.seed}-{a.condition}-measurement.json').open('x') as f:json.dump(audit,f);f.write('\n')
if __name__=='__main__':main()
