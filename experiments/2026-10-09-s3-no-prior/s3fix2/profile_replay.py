"""Saved S3 own-input replay. No renderer, simulator or eval-only input.

Profiling acquires the shared timing lock. Command/posterior hashes, not wall
speed, are the equivalence criterion. Expected historical HOST_ERROR retained.
"""
import argparse
import base64
import collections
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import subprocess
import time
import traceback

import numpy as np
from PIL import Image

from harness import zone_s3_continue_contract as contract
from harness.zone_s3_continue import Runtime
from harness.zone_s3_no_prior import IntegratedTrial, ROBOTS
from harness.zone_pair_highpose_exact_speedups import install


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=True).encode()).hexdigest()


def replay(raw, out, accelerated=False, *, measure=True):
    out.mkdir(parents=True, exist_ok=False)
    bundle=read(raw/'bundle.json'); scenario,mapped,sheet=contract.inputs()
    frames={r:lines(raw/f'robots/{r}/frames.jsonl') for r in ROBOTS}
    commands={r:lines(raw/f'robots/{r}/commands.jsonl') for r in ROBOTS}
    issued=collections.defaultdict(list)
    for r in ROBOTS:
        for row in commands[r][1:]:
            issued[round(row['t'],9)].append((r,{k:v for k,v in row.items() if k!='t'}))
    _,undo=install('v98-exact-v6'); rt=None; generated=[]; count=0; failure=None
    profile=cProfile.Profile() if measure else None
    start=time.monotonic() if measure else None
    if profile: profile.enable()
    try:
        rt=Runtime(contract.hp.resolve(bundle['map_id'])[0],sheet['orders'],contract.ROOT/bundle['calibration'],
            bundle['calibration_sha256'],seed=bundle['seed'],config=bundle['controller_config'])
        if accelerated:
            from harness.zone_s3_exact_cache import attach, OPTION
            for own in rt.localizers.values(): attach(own, exact_cache=OPTION)
        initial={r:{int(k):v for k,v in commands[r][0]['pulses'].items()} for r in ROBOTS}
        first=frames['r1'][0]['sim_time'];rt.initial_commands(first,initial)
        trial=IntegratedTrial(scenario,seed=bundle['seed'],links=rt.links,map_bundle=mapped,
            horizon_s=first+bundle['case_cap_s'],code_sha=bundle['source_sha'],pair_records=rt.pair.team.records)
        rt.trial=trial;trial.begin(first)
        for i, row in enumerate(frames['r1']):
            now=row['sim_time'];batch={}
            for r in ROBOTS:
                f=frames[r][i];assert f['sim_time']==now
                jpeg=(raw/f['path']).read_bytes();assert hashlib.sha256(jpeg).hexdigest()==f['sha256']
                obs={k:v for k,v in f.items() if k not in ('path','commanded_servo')}
                obs['image']=base64.b64encode(jpeg).decode()
                batch[r]=(obs,np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))
            rt.on_frames(now,batch);actions=rt.step(now)
            generated.append((now,actions))
            for r,a in issued[round(now,9)]:rt.on_command(r,now,a)
            count+=1
            if i%100==0: print(json.dumps(dict(frames=count,sim=now)),flush=True)
    except Exception:
        failure=traceback.format_exc()
    finally:
        wall=None
        if profile:
            profile.disable();wall=time.monotonic()-start
            profile.dump_stats(str(out/'profile.pstats'))
            with (out/'profile.txt').open('w') as stream:
                pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(100)
        if rt:
            state={r:dict(poses=own.pose_log,particles=hashlib.sha256(own.pose.provider.loc._pf.px.tobytes()).hexdigest(),
                weights=hashlib.sha256(own.pose.provider.loc._pf.logw.tobytes()).hexdigest(),
                rng=own.pose.provider.loc._pf.rng.bit_generator.state) for r,own in rt.localizers.items()}
            (out/'state.json').write_text(json.dumps(state,allow_nan=True)+'\n')
            report=dict(source=bundle['source_sha'],implementation_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                replay_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),raw=str(raw),accelerated=accelerated,simulation_runs=0,
                frames=count,profiled_wall_s=wall,timing_measured=measure,error=failure,generated_sha256=digest(generated),
                state_sha256=digest(state),robots={r:digest(s) for r,s in state.items()})
            (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            (out/'commands.json').write_text(json.dumps(generated)+'\n')
            rt.close();print(json.dumps(report),flush=True)
        undo()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--accelerated',action='store_true');a=p.parse_args()
    from scripts import agent_lock
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s3-no-prior-smoke',
        purpose='S3 saved-input cProfile, physics 0',pid=os.getpid(),expected_minutes=10,timing_sensitive=True)
    try:
        replay(Path('/Users/changmin/projects/ugrp/outputs/s3-continue-0a690821-s14201-v147'),a.output,a.accelerated)
    finally:
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        if a.output.exists(): (a.output/'lock.json').write_text(json.dumps(dict(acquired=held,released=released))+'\n')
