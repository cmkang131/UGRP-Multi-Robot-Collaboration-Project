"""Reuse exact own-RGB v42 loop, injecting only the preregistered noise option."""
import argparse
import importlib.util
import json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_consistency import attach,OPTION

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('old_rotation_replay',HERE/'replay_rotation_left.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('--option',choices=['off','on'],required=True)
    p.add_argument('--calibration',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-frames',type=int);a=p.parse_args()
    table=json.loads(a.calibration.read_text()) if a.calibration else None
    if a.option=='on':assert table['holdout']==a.seed and a.seed not in table['fit_seeds']
    def selected(runtime,**_):
        return attach(runtime,motion_noise=OPTION if a.option=='on' else 'off',calibration=table)
    replay=bind(old.replay,attach=selected,CRITERIA=HERE/'consistency-fit-criteria.json')
    replay(a.seed,a.option,a.output,a.max_frames)


if __name__=='__main__':main()
