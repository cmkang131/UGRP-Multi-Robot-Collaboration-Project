"""Assemble completed, retrieved evidence only; never upgrades missing outcomes."""
from pathlib import Path
import argparse,datetime,hashlib,json,subprocess

p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();state=a.state;exp=a.experiment
def read(path):
    if path.exists():return path.read_bytes()
    return subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
def obj(path):return json.loads(read(path))
def json_rows(path):
    try:return [json.loads(s) for s in read(path).splitlines() if s.strip()]
    except (FileNotFoundError,subprocess.CalledProcessError):return []
def zsave(path,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    subprocess.run(['zstd','-q','-f','-o',str(path)],input=raw,check=True)
    assert subprocess.check_output(['zstd','-dc',str(path)])==raw
    return {'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

summary=obj(exp/'summary.json');submissions=obj(state/'submissions.json')
archives=obj(state/'archive-verification.json');fetched=obj(state/'fetch-lite-verification.json')
details={};runs=[]
for submitted in submissions:
    name=submitted['run'];folder=Path('/Users/changmin/projects/ugrp/outputs/azure2-runs')/name
    s=obj(folder/'summary.json');r=s.get('result',{});meta=obj(folder/'RUN_META.json')
    assert name in archives and name in fetched and fetched[name]['checksum_verified']
    arc=archives[name];assert arc['proof']['verified'] and arc['proof']['files']==arc['proof']['hash_matches']
    try:score=obj(folder/'postrun-evaluation/evaluation.json')
    except (FileNotFoundError,subprocess.CalledProcessError):score={'status':'MISSING_POSTRUN_SCORE'}
    calls=obj(folder/'raw/llm/model_calls.json') if (folder/'raw/llm/model_calls.json').exists() or (folder/'raw/llm/model_calls.json.zst').exists() else []
    ledger=[v for v in json_rows(state/'upstream/openrouter/ledger.jsonl') if v.get('request_id','').split(':')[0]==name]
    progress=s['final_health']['progress'];initial=s.get('initial_check')
    milestones=dict(r.get('stage_milestones') or {});candidate=[];stages={}
    for rid in ('r1','r2'):
        own=json_rows(folder/f'raw/robots/{rid}/ownmap.jsonl')
        candidate.extend(x['t'] for x in own if x.get('remembered_B'))
        stages[rid]=dict(last=own[-1].get('stage') if own else None,first_reached_sim_s={})
        for x in own:stages[rid]['first_reached_sim_s'].setdefault(x['stage'],x['t'])
    outcomes={k:bool(r.get(k,False)) for k in ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')}
    furthest=('start_to_finish_transport' if outcomes['start_to_finish_transport'] else 'own_map_route'
        if outcomes['own_map_completed'] else 'B_boundary' if progress.get('own_B_boundary_remembered')
        else 'B_candidate_before_boundary_confirmation' if candidate else 'mapping')
    cost=sum((c.get('provider_usage') or {}).get('cost') or 0 for c in calls)
    run=dict(id=name,condition=meta['condition'],seed=meta['seed'],source_sha=meta['sha'],
        status=r.get('status','HOST_ERROR'),exit=s['exit'],cause=r.get('failure') or r.get('controller_failure'),
        sim_s=r.get('sim_s'),wall_s=r.get('wall_s'),wall_per_sim=r.get('wall_s',0)/r['sim_s'] if r.get('sim_s') else None,
        frames=r.get('frames'),stage_milestones=milestones,navigation_stages=stages,
        first_B_candidate_sim_s=min(candidate) if candidate else None,furthest_stage=furthest,
        initial_check=initial,boundary_values=s['final_health'].get('boundary'),
        evaluation={rid:{k:v for k,v in value.items() if k in ('status','map_error_m','control_error_m','stall_duration_s','gated_frames')}
                    for rid,value in score.items() if isinstance(value,dict)},
        model=dict(calls=len(calls),ledger_entries=len(ledger),known_cost_usd=cost,
            missing_cost_calls=sum((c.get('provider_usage') or {}).get('cost') is None for c in calls),
            prompt_tokens=sum((c.get('provider_usage') or {}).get('prompt_tokens',0) for c in calls),
            completion_tokens=sum((c.get('provider_usage') or {}).get('completion_tokens',0) for c in calls)),
        raw='azure2:/home/ugrp/ugrp-sim/runs/'+name,arm_raw='oracle-codex:'+arc['proof']['native_arm_path'],
        result_sha256=hashlib.sha256(read(folder/'raw/result.json')).hexdigest() if r else None,archive=arc['proof'],**outcomes)
    runs.append(run);details[name]=dict(summary=s,score=score,model_calls=calls,provider_ledger=ledger,archive=arc,fetch=fetched[name])
summary.update(status='COMPLETE_WITH_FAILURES' if not all(r['E2E_success'] for r in runs) else 'COMPLETE',
    runs=runs,completed=len(runs),unfinished=0,outcomes=dict(N=len(runs),**{k:sum(r[k] for r in runs)
        for k in ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')}),
    retrieval=dict(completed=len(fetched),expected=len(submissions),files=sum(v['proof']['files'] for v in archives.values()),
        hash_matches=sum(v['proof']['hash_matches'] for v in archives.values()),mac_lite_bytes=sum(v['bytes'] for v in fetched.values())),
    model_accounting=dict(calls=sum(r['model']['calls'] for r in runs),known_cost_usd=sum(r['model']['known_cost_usd'] for r in runs),
        missing_cost_calls=sum(r['model']['missing_cost_calls'] for r in runs)),
    last_recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
if (state/'deallocated.json').exists():summary['vm']=obj(state/'deallocated.json')
summary['artifacts']=[zsave(exp/'run-details.json.zst',details)]
# Large initial command diagnostics remain in detail; main summary stays compact.
for run in summary['runs']:
    if run['initial_check']:
        run['initial_check']={k:v for k,v in run['initial_check'].items() if k in ('passed','checks','elapsed_since_submit_s','actual_displacement_m')}
(exp/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(outcomes=summary['outcomes'],retrieval=summary['retrieval'],model=summary['model_accounting']),ensure_ascii=False))
