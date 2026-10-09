"""Exact saved-input comparison; timing is optional and exclusively locked."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

from harness.zone_final_pair_binding import bind
from harness.zone_s3_exact_cache import attach


def replay(raw, out, mode, *, measure=False):
    path=Path(__file__).parents[1]/'s3fix2/profile_replay.py'
    spec=importlib.util.spec_from_file_location('saved_s3_replay',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    audits={}
    def runtime(*a,**kw):
        rt=old.Runtime(*a,**kw)
        for rid, own in rt.localizers.items():
            attach(own,exact_cache=mode)
            audits[rid]=getattr(own,'s3_exact_cache',{})
        return rt
    bind(old.replay,Runtime=runtime)(raw,out,False,measure=measure)
    result=json.loads((out/'result.json').read_text())
    result.update(exact_cache=mode,cache_audit=audits)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cache',choices=['off','posterior_content_v1','posterior_content_v2'],required=True)
    p.add_argument('--measure',action='store_true');a=p.parse_args()
    held=None
    if a.measure:
        from scripts import agent_lock
        held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s3-no-prior-smoke',
            purpose='S3 offline exact cache cProfile; physics 0',pid=os.getpid(),expected_minutes=10,timing_sensitive=True)
    try:
        replay(a.raw,a.output,a.cache,measure=a.measure)
    finally:
        if held:
            released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
            (a.output/'lock.json').write_text(json.dumps(dict(acquired=held,released=released))+'\n')
