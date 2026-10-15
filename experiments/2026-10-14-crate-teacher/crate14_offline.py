"""Saved-ledger and static kinematic analysis only. No physics/render/remote.

Baseline replay must match the ledger in full. Candidate trajectory replay stops
at its first divergence. Independent alignment snapshots use the SAME recorded
observation and old state; they predict decisions, never subsequent motion.
"""
import hashlib,json,math,random,subprocess,sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from scripts.run_crate_teacher import make_grasp_teacher
from sim.crate_observation_v12 import tagged_world
from sim.cargo_teacher_profile import CRATE
from sim.crate_alignment_v14 import MODE,STATION_M,stance_valid,pick_closed_pwm,lift_feasible
from sim.grasp_act_teacher import local,wrap
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
HERE=Path(__file__).parent
ANALYSIS=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate13-727de2af')

def read(p):
    p=Path(p)
    if not p.exists():p=Path(str(p)+'.zst')
    return subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
def js(p):return json.loads(read(p))
def rows(p):return [json.loads(l) for l in read(p).splitlines()]
def sha(p):return hashlib.sha256(read(p)).hexdigest()

def enable(t):
    t.crate_alignment=MODE;t.staging_distance=STATION_M
    t.approach_choice=(t.approach_choice[0],STATION_M);t.approach_distances=(STATION_M,)
    t.approach_grasp_filter=lambda w,p:stance_valid(w,t.rid,t.end,p)
    return t


def replay(name,candidate=False,snapshots=False):
    raw=RAW/name/'raw';res=js(raw/'result.json')
    ev=[r for r in rows(raw/'eval-only.jsonl') if r['stage']=='grasp']
    roles=res.get('prefix',{}).get('assigned') or {'r1':'teal','r2':'blue'}
    lab={r:[v for v in rows(raw/f'teacher-{r}.jsonl') if 'clean_teacher_command' in v] for r in roles}
    keys=('teacher_stability','teacher_search','approach_goal_set','crate_lift_pose','crate_approach_recovery',
          'crate_wall_footprint','crate_stances','crate_pulse_safety','crate_candidate_recovery')
    opts={k:res.get(k,'off') for k in keys}
    if candidate:opts['crate_alignment']=MODE
    ts={r:make_grasp_teacher(r,e,lab[r][0]['applied_command']['pwm'],**opts) for r,e in roles.items()}
    ms={r:VisibleWorld(r,e,profile=CRATE,static_walls=res['static_walls']) for r,e in roles.items()}
    audit=new_input_audit(True,'issued');clocks={r:IssuedClock() for r in roles}
    rng=random.Random(js(raw/'plan.json')['seed']);delays={'r1':0.,'r2':rng.uniform(0,1.5)}
    sync=GraspStartSync(tuple(roles),res.get('grasp_start_delays_s') or delays)
    lift=GraspStartSync(tuple(roles),{r:0. for r in roles})
    differences=[];checked=0;total=0;decisions=[];examples=[]
    for i,row in enumerate(ev):
        now=row['t'];holding=any(t.phase in ('lift','complete') for t in ts.values())
        plain={r:ms[r].observe(row['visible_measurements'][r],now) for r in roles}
        ws={r:AuditedTeacherInput(tagged_world(plain[r],holding=holding),audit,provenance='value_sources_v1') for r in roles}
        permits=sync.tick({r:t.prepare_signal(ws[r],now) for r,t in ts.items()},now)
        lifts=lift.tick({r:t.lift_ready() for r,t in ts.items()},now)
        for r,t in ts.items():
            prev=lab[r][max(0,i-1)]['applied_command']
            skill='wait' if ((t.phase=='ready' and not permits[r]) or (t.phase=='closed' and not lifts[r])) else 'grasp'
            c=clocks[r].observe((skill,t.end,t.handoff),now,prev['pwm']);t.skill_started=now-c['skill_elapsed_s']
            before=t.phase
            shadow=enable(deepcopy(t)) if snapshots and before in ('align','ready') and plain[r]['beam'] is not None else None
            cmd,done=t.step(ws[r],now,permit_pick=permits[r],permit_lift=lifts[r]);exp=lab[r][i]['clean_teacher_command']
            same=(all(cmd[k]==exp[k] for k in ('t','wheels','pwm'))
                  and all(abs(a-b)<=1e-10 for a,b in zip(cmd['duration_s'],exp['duration_s']))
                  and done==lab[r][i]['done'] and t.phase==lab[r][i]['teacher_phase'])
            checked+=int(same);total+=1
            if not same:differences.append({'tick':i,'t':now,'robot':r,'before':before,'old_phase':lab[r][i]['teacher_phase'],
                'new_phase':t.phase,'old_wheels':exp['wheels'],'new_wheels':cmd['wheels'],
                'old_duration_s':exp['duration_s'],'new_duration_s':cmd['duration_s'],
                'changed_fields':[k for k in ('wheels','duration_s','pwm') if cmd[k]!=exp[k]]})
            if shadow is not None and plain[r]['visibility'][r]['visible_probes']>=5:
                w=plain[r];pose,g,heading,_=shadow._geometry(w);x,y=local(pose,g)
                # Snapshot alignment law, without claiming the changed trajectory
                # would have reached this baseline state or kept its old stance.
                new,ready=shadow._approach(w,now)
                decision={'t':now,'rid':r,'phase_before':before,'old_zero':not any(cmd['wheels']),
                    'new_zero':not any(new['wheels']),'old_ready':t.ready_geometry(w),'new_ready':shadow.ready_geometry(w),
                    'x_m':x,'y_m':y,'z_m':g[2],'old_stance_deg':math.degrees(shadow.approach_choice[0]),
                    'candidate_stance_valid':stance_valid(w,r,t.end,(*shadow._geometry(w)[3],heading)),
                    'new_active':shadow.align_active,'new_outcome':shadow.outcome}
                decisions.append(decision)
                if decision['old_zero'] and not decision['new_zero'] and len(examples)<2:
                    examples.append({'world':w,'rid':r,'end':t.end,'decision':decision})
            t.remember_applied(lab[r][i]['applied_command']);ms[r].issue(lab[r][i]['applied_command'])
        if differences:break
    counts={}
    for r in roles:
        subset=[d for d in decisions if d['rid']==r]
        a=[d for d in subset if d['phase_before']=='align']
        counts[r]={'align_N':len(a),'align_old_zero':sum(d['old_zero'] for d in a),
            'align_new_zero':sum(d['new_zero'] for d in a),'zero_to_motion':sum(d['old_zero'] and not d['new_zero'] for d in a),
            'snapshots_N':len(subset),'old_ready':sum(d['old_ready'] for d in subset),'new_ready':sum(d['new_ready'] for d in subset),
            'candidate_rejects_old_stance':sum(not d['candidate_stance_valid'] for d in subset)}
    return {'run':name,'candidate':candidate,'matched':checked,'total':total,'full_baseline_match':not differences,
            'first_divergence':differences,'alignment':counts,'snapshot_examples':examples,'snapshot_decisions':decisions,
            'saved_status':res['status'],'saved_outcomes':res.get('prefix',{}).get('outcomes'),'input_audit':audit,'input_sha256':{f:sha(raw/f) for f in ('result.json','plan.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl')}}


def main():
    import mujoco
    def forbidden(*a,**k):raise RuntimeError('physics/render forbidden in crate14 offline analysis')
    for k in ('mj_step','mj_forward','Renderer'):setattr(mujoco,k,forbidden)
    out=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate14-audit');out.mkdir(exist_ok=True)
    summary={'scope':'offline saved decision replay + numerical/static rays only; no physical/student success',
             'source_baseline':'727de2af0e5ec10dda0b954e757c2fe42e694766','runs':[],
             'source_analysis_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted([*ANALYSIS.glob('*.json'),*(ANALYSIS/'scripts').glob('*.py')])}}
    summary['source_analysis_sha256'][str(ANALYSIS/'report.md')]=sha(ANALYSIS/'report.md')
    observed_z=[]
    for seed in (79317,79316):
        name=f'crate-diag-{seed}-727de2af'
        b=replay(name,snapshots=True);c=replay(name,candidate=True)
        assert b['full_baseline_match'],b['first_divergence']
        path=out/f'replay-{seed}.json.zst'
        raw=(json.dumps({'baseline':b,'candidate_prefix':c},separators=(',',':'))+'\n').encode()
        packed=subprocess.check_output(['zstd','-q','-c'],input=raw)
        assert subprocess.check_output(['zstd','-q','-d','-c'],input=packed)==raw
        path.write_bytes(packed)
        observed_z.extend(d['z_m'] for d in b['snapshot_decisions'])
        summary['runs'].append({k:v for k,v in b.items() if k not in ('snapshot_decisions','snapshot_examples')})
        summary['runs'][-1].update(candidate_first_divergence=c['first_divergence'],detail=str(path),detail_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),detail_uncompressed_sha256=hashlib.sha256(raw).hexdigest())
        print(seed,b['matched'],b['total'],b['alignment'],flush=True)
    summary['observed_grasp_z_m']={'min':min(observed_z),'max':max(observed_z),'N':len(observed_z)}
    z_values=sorted({.02396,min(observed_z),max(observed_z)})
    windows=[]
    from itertools import product
    for z,y in product(z_values,(0.,.004,.012,.0167)):
        xs=[round(.190+i*.0001,7) for i in range(161)]
        good=[x for x in xs if lift_feasible(x,y,z)]
        windows.append({'y_m':y,'z_m':z,'min_x_m':min(good),'max_x_m':max(good),
                        'step_m':.0001,'command_source':'exact planned final descent PWM, then close 1500; same as _queue_pick'})
    summary['execution_pose_lift_windows']=windows
    summary['source_code_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'sim/crate_alignment_v14.py',ROOT/'sim/crate_grasp_teacher.py',ROOT/'sim/grasp_act_teacher_v3.py',ROOT/'scripts/make_crate_teacher_plan.py',ROOT/'scripts/run_crate_teacher.py']}
    (HERE/'crate14-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
