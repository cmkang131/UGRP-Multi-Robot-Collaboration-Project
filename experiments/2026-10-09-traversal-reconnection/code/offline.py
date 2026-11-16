"""Reuse egomap51 exact input adapter / sealed GT audit / unchanged gates."""
from pathlib import Path
import importlib.util,json,argparse,os
ROOT=Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0,str(ROOT))
from harness.own_traversal_reconnection import ReconnectedGraph,PartialReturn
SPEC=importlib.util.spec_from_file_location('egomap51_offline',ROOT/'experiments/2026-10-09-own-traversal-return/code/offline.py')
legacy=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(legacy)
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/traversal-reconnection-v1')


class ProgressGraph(ReconnectedGraph):
    def observe(self,*a,**kw):
        super().observe(*a,**kw)
        if self.frames%250==0:print('prefix',self.frames,'nodes',len(self.nodes),'matches',len(self.reconnections),flush=True)


legacy.RAW=RAW;legacy.EXP=EXP
legacy.TraversalGraph=ProgressGraph
legacy.TraversalReturn=PartialReturn


def predict(seed):
    assert os.getpriority(os.PRIO_PROCESS,0)==0
    legacy.predict(seed)


def score(seed):return legacy.score(seed)


def gate():
    legacy.gate()  # exact egomap51 conjunction, including first-frame requirement
    p=EXP/'results/gate.json';g=legacy.load(p)
    g['condition_prereg_commit']='a068cf73'
    legacy.dump(p,g)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','score','gate']);p.add_argument('--seed',type=int,choices=range(49001,49007));a=p.parse_args()
    if a.mode=='predict':predict(a.seed)
    elif a.mode=='score':score(a.seed)
    else:gate()
