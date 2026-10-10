"""Frozen saved-input consumers, one diversity option; simulator/GT absent."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

from harness import pf_resampling_diversity as diversity
from harness.zone_final_pair_binding import bind

HERE = Path(__file__).parent


def load(name):
    path = HERE.parent/'s3fix6'/name
    spec = importlib.util.spec_from_file_location('prior_'+path.stem,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def replay_s3(raw, out, option):
    prior = load('replay_s3.py')
    def runtime(*args,config,**kwargs):
        plain = copy.deepcopy(config)
        plain['options']['observation_consistency'] = 'off'
        rt = prior.Runtime(*args,config=plain,**kwargs)
        for own in rt.localizers.values(): diversity.attach_s3(own,resampling_diversity=option)
        return rt
    bind(prior.replay,Runtime=runtime)(raw,out,option)
    path=out/'result.json'
    result=json.loads(path.read_text())
    result.update(observation_consistency='off',resampling_diversity=option)
    path.write_text(json.dumps(result,indent=2)+'\n')


def replay_ownmap(raw,out,adapter,option):
    prior = load('replay_ownmap.py')
    def attach(grid,*,observation_consistency):
        diversity.attach_ownmap(grid,resampling_diversity=option)
        if option != 'off': grid.observation_consistency_audit = grid.resampling_diversity_audit
        return grid
    bind(prior.replay,attach_ownmap=attach)(raw,out,adapter,option)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['s3','ownmap'],required=True)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--adapter',type=Path);p.add_argument('--option',choices=diversity.OPTIONS,required=True)
    a=p.parse_args()
    if a.kind == 's3': replay_s3(a.raw,a.output,a.option)
    else: replay_ownmap(a.raw,a.output,a.adapter,a.option)
