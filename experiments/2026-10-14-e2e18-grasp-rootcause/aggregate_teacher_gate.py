"""Read-only audit of distinct frozen teacher trials across continued batches."""
import argparse,hashlib,json,math,statistics,subprocess
from collections import Counter
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    if not p.exists():p=Path(str(p)+'.zst')
    b=p.read_bytes()
    return json.loads(subprocess.check_output(['zstd','-qdc'],input=b) if p.suffix=='.zst' else b)


def distribution(xs):
    xs=sorted(xs)
    def q(p):
        at=p*(len(xs)-1);a=math.floor(at);b=math.ceil(at)
        return xs[a]+(xs[b]-xs[a])*(at-a)
    return {'N':len(xs),'min':min(xs),'median':statistics.median(xs),'p95':q(.95),'max':max(xs)} if xs else {'N':0}


def aggregate(roots,plan_path,component_path):
    plan=read(plan_path);expected={e['episode_id']:e for e in plan['episodes']}
    proof=read(component_path);baseline=proof['sha256'];rows=[];excluded=[];seen=set();components={}
    for root in roots:
        for raw in sorted(root.glob('cohort-*/episode-*/raw')):
            if not (raw/'result.json').exists():excluded.append({'raw':str(raw),'status':'missing_result'});continue
            result=read(raw/'result.json')
            if result['status']!='complete':excluded.append({'raw':str(raw),'status':result['status']});continue
            setup=read(raw/'plan.json');eid=setup['episode_id']
            if eid not in expected or setup!=expected[eid]:raise ValueError('frozen setup mismatch '+str(raw))
            if eid in seen:raise ValueError('duplicate completed frozen start '+eid)
            source=result['source_sha'];src=root.parents[1]/'src'/source
            if source not in components:
                actual={name:sha(src/name) for name in baseline}
                if actual!=baseline:raise ValueError('teacher/scene/port/contract/physics bytes changed')
                components[source]=actual
            manifest=read(raw/'manifest.json')
            for rel,entry in manifest.items():
                path=raw/rel
                if not path.resolve().is_relative_to(raw.resolve()) or sha(path)!=entry['sha256']:
                    raise ValueError('raw evidence hash mismatch '+str(path))
                if 'decoded_sha256' in entry:
                    decoded=subprocess.check_output(['zstd','-qdc',str(path)])
                    if hashlib.sha256(decoded).hexdigest()!=entry['decoded_sha256']:
                        raise ValueError('decoded evidence hash mismatch '+str(path))
            # The original parent was interrupted after all child workflows
            # completed. Their preserved canonical receipts settle the exit,
            # without inventing a missing per-child EXIT file.
            receipts=[p for p in raw.parent.glob('management/*/manifest.json') if read(p).get('exit_code')==0 and read(p).get('status')=='process_completed']
            if len(receipts)!=1:raise ValueError('one completed canonical workflow receipt required '+str(raw))
            receipt=read(receipts[0])
            if receipt.get('physical_success')!=result['physical_success']:raise ValueError('workflow/physical result mismatch')
            if result.get('student_execution') is not False or result.get('weld')!='off' or result.get('recording_mode')!='success_measurement':
                raise ValueError('wrong trial type')
            if result['observation_sampling']['rgb_hz']!=0:raise ValueError('student RGB was enabled in gate')
            seen.add(eid)
            m=raw/('manifest.json' if (raw/'manifest.json').exists() else 'manifest.json.zst')
            rows.append({'episode_id':eid,'seed':setup['seed'],'index':next(i for i,e in enumerate(plan['episodes']) if e['episode_id']==eid),
                'source_sha':source,'raw':'azure3:'+str(raw),'result_sha256':sha(raw/'result.json'),
                'manifest_path':'azure3:'+str(m),'manifest_sha256':sha(m),'verified_files':len(manifest),
                'workflow_receipt':'azure3:'+str(receipts[0]),'workflow_receipt_sha256':sha(receipts[0]),
                'physical_success':result['physical_success'],'joint_held':result['joint_held'],
                'sim_s':result['sim_s'],'wall_s':result['wall_s'],'wall_per_sim':result['wall_per_sim'],
                'teachers':result['teachers'],'first_attempt':result['first_attempt']})
    rows.sort(key=lambda r:r['index']);n=sum(r['physical_success'] for r in rows);N=len(rows)
    phases={}
    for rid in ('r1','r2'):
        phases[rid]={phase:{'n':sum(any(e['to']==phase for e in r['teachers'][rid]['events']) for r in rows),'N':N}
                     for phase in ('align','ready','pick','verify','done')}
    failures=[r for r in rows if not r['physical_success']]
    return {'schema':'ugrp.grasp_act.verified_teacher_gate.v1','object_kind':'long_beam','n':n,'N':N,'planned_N':len(expected),
        'qualified':N==len(expected) and N>=40 and n/N>=.95,'first_attempt_n':sum(r['physical_success'] and r['first_attempt'] for r in rows),
        'missing_episode_ids':sorted(set(expected)-seen),'excluded':excluded,'rows':rows,'teacher_stage_funnel':phases,
        'failure_episode_N':len(failures),
        'failure_outcomes':dict(Counter(t['outcome'] for r in failures for t in r['teachers'].values() if t['outcome']!='success')),
        'episode_sim_s':distribution([r['sim_s'] for r in rows]),'success_sim_s':distribution([r['sim_s'] for r in rows if r['physical_success']]),
        'wall_per_sim':distribution([r['wall_per_sim'] for r in rows]),
        'plan_sha256':sha(plan_path),'identical_execution_components':components,'baseline_source_sha':proof['baseline_sha'],
        'student_rgb_frames':0,'data_episodes':0,'student_physical_trials':0,
        'scope':'privileged teacher grasp only; no carry/release, student, or LLM success claim'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--roots',type=Path,nargs='+',required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--components',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=aggregate(a.roots,a.plan,a.components);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('n','N','qualified','episode_sim_s','wall_per_sim','failure_outcomes','missing_episode_ids')}))
