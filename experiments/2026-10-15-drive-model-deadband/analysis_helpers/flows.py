import sys,json,math,os
sys.dont_write_bytecode=True
from lib import *
G='/Users/changmin/projects/ugrp/outputs/gcp1-runs'
BEAM='/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/beam-gate-752b0cbb/raw/grasp-search-gate40-gcp-752b0cbb'
def jl(p):return [json.loads(x) for x in zl(p)]
def load_robots_flow(d,kind):
    """beam/crate (applied_command) or release (wheels/wheel_until). returns {rid:(ev_t,gt,cmds,phase)}"""
    ev=[e for e in jl(find(d,'eval-only.jsonl')) if 'robots' in e]
    res={}
    for r in ('r1','r2'):
        p=find(d,f'teacher-{r}.jsonl')
        if not p:continue
        led=jl(p);cmds={}
        for row in led:
            if 'applied_command' in row:
                c=row['applied_command'];cmds[round(c['t'],3)]=(c['wheels'],c['duration_s'],row.get('teacher_phase'))
            else:
                t=row['t'];w=row['wheels'];u=row['wheel_until']
                cmds[round(t,3)]=(w,[max(0.,uu-t) if ww else 0. for ww,uu in zip(w,u)],row.get('teacher_phase'))
        ev_t=[e['t'] for e in ev];gt=[tuple(e['robots'][r]['pose']) for e in ev]
        ph=[e.get('stage') or e.get('phase') for e in ev]
        res[r]=(ev_t,gt,cmds,ph,led)
    return res
def beam_runs():
    for ep in range(16,56):
        d=f'{BEAM}/cohort-{(ep//16)*16:03d}/episode-{ep:03d}/raw'
        yield f'beam-{ep}',load_robots_flow(d,'applied')
def gcp_runs(prefix,kind,exclude=()):
    for run in sorted(os.listdir(G)):
        if run.startswith(prefix) and not any(run.startswith(x) for x in exclude):
            d=rawdir(f'{G}/{run}')
            if not find(d,'eval-only.jsonl'):continue
            yield run,load_robots_flow(d,kind)

def load_solo(d):
    ev=[e for e in jl(find(d,'eval-only.jsonl')) if 'base_xyz' in e]
    led=jl(find(d,'teacher-commands.jsonl'))
    plan=json.load(open(d+'/plan.json'))
    cmds={}
    for row in led:
        c=row['command'];cmds[round(c['t'],3)]=(c['wheels'],c['duration_s'],row.get('phase'))
    ev_t=[e['t'] for e in ev]
    y0=plan['spawns'][plan.get('robot_id','r1')][3]
    gt=[(e['base_xyz'][0],e['base_xyz'][1],None) for e in ev]
    ph=[e.get('evaluation_phase') for e in ev]
    return {'r1':(ev_t,gt,cmds,ph,led)},y0
def solo_runs(prefix,exclude=()):
    for run in sorted(os.listdir(G)):
        if run.startswith(prefix) and not any(run.startswith(x) for x in exclude):
            d=rawdir(f'{G}/{run}')
            if not find(d,'teacher-commands.jsonl') or not find(d,'eval-only.jsonl'):continue
            try:rr,y0=load_solo(d)
            except Exception as e:print('skip',run,e);continue
            yield run,rr,y0
