"""Assemble completed, retrieved evidence only; never upgrades missing outcomes."""
from pathlib import Path
import argparse,datetime,hashlib,json,subprocess

p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();state=a.state;exp=a.experiment
def read(path):
    if path.exists():return path.read_bytes()
    return subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
def obj(path):return json.loads(read(path))
def optional_obj(path):
    return obj(path) if path.exists() or Path(str(path)+'.zst').exists() else None
def json_rows(path):
    try:return [json.loads(s) for s in read(path).splitlines() if s.strip()]
    except (FileNotFoundError,subprocess.CalledProcessError):return []
def progress_rows(folder):
    paths=sorted({p.with_suffix('') if p.suffix=='.zst' else p
                  for p in folder.glob('management/*/console.log*')})
    if not paths:paths=[folder/'log.txt']
    result=[]
    for path in paths:
        for line in read(path).splitlines():
            if not line.lstrip().startswith(b'{'):continue
            try:value=json.loads(line)
            except json.JSONDecodeError:continue
            if isinstance(value,dict) and all(k in value for k in ('sim_s','wall_s','phase','robots')):
                result.append(value)
    return sorted(result,key=lambda x:x['wall_s'])
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
    samples=progress_rows(folder)
    for value in samples:
        if value.get('own_map_B_generated'):
            milestones.setdefault('B_candidate',dict(sim_s=value['sim_s'],wall_s=value['wall_s'],
                timing='first recorded progress sample; one-SIM-second sampling'))
        for rid in stages:
            if rid in value['robots']:
                stages[rid].setdefault('first_sampled_wall_s',{}).setdefault(
                    value['robots'][rid]['stage'],value['wall_s'])
    outcomes={k:bool(r.get(k,False)) for k in ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')}
    furthest=('start_to_finish_transport' if outcomes['start_to_finish_transport'] else 'own_map_route'
        if outcomes['own_map_completed'] else 'B_boundary' if progress.get('own_B_boundary_remembered')
        else 'B_candidate_before_boundary_confirmation' if candidate else 'mapping')
    # The forwarding ledger includes charged replies even if shutdown prevented
    # the controller from settling a call. Preserve missing usage as unknown.
    cost=sum((c.get('openrouter') or {}).get('cost') or 0 for c in ledger)
    driver_ids={str(c['call_id']) for c in calls if c.get('call_id') is not None}
    forwarded_ids={c['request_id'].split(':')[1] for c in ledger}
    health_stop=optional_obj(folder/'HEALTH_STOP.json')
    host_error=optional_obj(folder/'HOST_ERROR.json')
    finalized=r.get('finalization_complete') is True
    run=dict(id=name,condition=meta['condition'],seed=meta['seed'],source_sha=meta['sha'],
        status=r.get('status','HOST_ERROR') if finalized else 'HOST_ERROR',
        source_result_status=r.get('status'),finalization_complete=finalized,
        exit=s['exit'],cause=(health_stop or {}).get('reason') or r.get('failure') or r.get('controller_failure')
            or ('INCOMPLETE_FINALIZATION' if not finalized else None),
        supervisor_host_error=host_error,health_stop=health_stop,
        submitted_unix=meta['started_unix'],
        sim_s=r.get('sim_s'),wall_s=r.get('wall_s'),wall_per_sim=r.get('wall_s',0)/r['sim_s'] if r.get('sim_s') else None,
        frames=r.get('frames'),stage_milestones=milestones,navigation_stages=stages,
        wall_stage_timing='Recorded one-SIM-second progress samples; raw first candidate SIM time separately retained',
        first_B_candidate_sim_s=min(candidate) if candidate else None,furthest_stage=furthest,
        initial_check=initial,boundary_values=s['final_health'].get('boundary'),
        evaluation={rid:{k:v for k,v in value.items() if k in ('status','map_error_m','control_error_m','stall_duration_s','gated_frames')}
                    for rid,value in score.items() if isinstance(value,dict)},
        model=dict(calls=len(calls),ledger_entries=len(ledger),known_cost_usd=cost,
            cost_source='Mac OpenRouter forwarding ledger, reported provider usage',
            missing_cost_calls=sum((c.get('openrouter') or {}).get('cost') is None for c in ledger),
            driver_missing_cost_calls=sum((c.get('provider_usage') or {}).get('cost') is None for c in calls),
            driver_known_cost_usd=sum((c.get('provider_usage') or {}).get('cost') or 0 for c in calls),
            forwarded_without_driver_record=sorted(forwarded_ids-driver_ids),
            driver_without_forward_record=sorted(driver_ids-forwarded_ids),
            http_attempts=sum(len((c.get('openrouter') or {}).get('attempts',[])) for c in ledger),
            earlier_attempts_without_separate_cost=sum(max(0,len((c.get('openrouter') or {}).get('attempts',[]))-1) for c in ledger),
            prompt_tokens=sum((c.get('openrouter') or {}).get('prompt_tokens') or 0 for c in ledger),
            completion_tokens=sum((c.get('openrouter') or {}).get('completion_tokens') or 0 for c in ledger)),
        raw='azure2:/home/ugrp/ugrp-sim/runs/'+name,arm_raw='oracle-codex:'+arc['proof']['native_arm_path'],
        result_sha256=hashlib.sha256(read(folder/'raw/result.json')).hexdigest() if r else None,archive=arc['proof'],**outcomes)
    runs.append(run);details[name]=dict(summary=s,run_meta=meta,score=score,model_calls=calls,provider_ledger=ledger,archive=arc,fetch=fetched[name])
summary.update(status='COMPLETE_WITH_FAILURES' if not all(r['E2E_success'] for r in runs) else 'COMPLETE',
    runs=runs,completed=len(runs),unfinished=0,outcomes=dict(N=len(runs),**{k:sum(r[k] for r in runs)
        for k in ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')}),
    retrieval=dict(completed=len(fetched),expected=len(submissions),files=sum(v['proof']['files'] for v in archives.values()),
        hash_matches=sum(v['proof']['hash_matches'] for v in archives.values()),mac_lite_bytes=sum(v['bytes'] for v in fetched.values())),
    model_accounting=dict(calls=sum(r['model']['calls'] for r in runs),known_cost_usd=sum(r['model']['known_cost_usd'] for r in runs),
        cost_source='Mac OpenRouter forwarding ledger, reported provider usage',
        upstream_forwards=sum(r['model']['ledger_entries'] for r in runs),
        http_attempts=sum(r['model']['http_attempts'] for r in runs),
        missing_cost_calls=sum(r['model']['missing_cost_calls'] for r in runs),
        earlier_attempts_without_separate_cost=sum(r['model']['earlier_attempts_without_separate_cost'] for r in runs)),
    last_recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
summary['condition_outcomes']={condition:dict(N=len(group),**{
    key:sum(run[key] for run in group) for key in
    ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')})
    for condition in sorted({run['condition'] for run in runs})
    for group in [[run for run in runs if run['condition']==condition]]}
if (state/'deallocated.json').exists():
    vm=obj(state/'deallocated.json')
    proofs=state/'provisioning-time-proofs'
    created=obj(proofs/'creation-time.json')['created']
    idle=obj(proofs/'idle-deallocated.json')['utc']
    restarted=obj(proofs/'long-start-request.json')['utc']
    timestamp=lambda value:datetime.datetime.fromisoformat(value).timestamp()
    intervals=[dict(purpose='provisioning_and_idle_guard_verification',start=created,end=idle),
               dict(purpose='long_cohort_and_archive_retrieval',start=restarted,end=vm['deallocated_verified_utc'])]
    for interval in intervals:
        interval['observed_interval_s']=timestamp(interval['end'])-timestamp(interval['start'])
    vm.update(observed_allocation_intervals=intervals,
        observed_total_s=sum(x['observed_interval_s'] for x in intervals),
        boot_to_deallocate_request_s=timestamp(vm['deallocate_requested_utc'])-vm['boot_unix'],
        usage_scope='Observed request/verification intervals; not metered billing. Includes provisioning and retrieval.',
        compute_cost_estimate_usd=sum(x['observed_interval_s'] for x in intervals)/3600*vm['rate_usd_per_h'],
        estimate_scope='User-provided hourly compute rate; disk, snapshot, public IP and traffic excluded.')
    summary['vm']=vm
summary['artifacts']=[zsave(exp/'run-details.json.zst',details)]
batch_path=state/'remote-batch-evidence.json.zst'
batch=json.loads(subprocess.check_output(['zstd','-dc',str(batch_path)]))
checkpoints=[json.loads(line) for line in batch['files']['e2e13-long-progress.jsonl'].splitlines() if line]
summary['monitoring']=dict(checkpoints=len(checkpoints),
    checkpoints_per_run={run['id']:sum(x['run']==run['id'] for x in checkpoints) for run in runs},
    initial_checks_passed=sum(bool(run['initial_check'] and run['initial_check']['passed']) for run in runs),
    controller_interventions_after_initial_check=0,
    authorized_wall_cap_stops=sum(run['cause']=='AUTHORIZED_SEVEN_HOUR_WALL_CAP' for run in runs),
    tunnel_starts=sum(row['event']=='START' for row in json_rows(state/'tunnel/events.jsonl')),
    network_note='Mac tunnel disconnected and reconnected; remote runs and periodic checkpoints continued. No additional model attempts beyond the 18 reconciled calls.')
summary['operational_evidence']=zsave(exp/'operational-evidence.json.zst',dict(
    submissions=submissions,archives=archives,fetch_lite=fetched,
    deallocated=optional_obj(state/'deallocated.json'),relay_cleanup=optional_obj(state/'relay-cleanup.json'),
    tunnel_events=json_rows(state/'tunnel/events.jsonl'),infra_ci=optional_obj(state/'infra-ci.json'),
    provisioning_proofs={path.name:obj(path) for path in (state/'provisioning-time-proofs').glob('*.json')}))
summary['artifacts'].append(summary['operational_evidence'])
for source in [batch_path,*sorted((state/'archive-inventories').glob('*.json.zst'))]:
    compressed=source.read_bytes();raw=subprocess.check_output(['zstd','-dc',str(source)])
    if source.parent.name=='archive-inventories':
        name=source.name.removesuffix('.json.zst')
        assert hashlib.sha256(raw).hexdigest()==archives[name]['archive_marker_sha256']
        destination=exp/'archive-inventories'/source.name
    else:
        assert hashlib.sha256(raw).hexdigest()==summary['vm']['batch_evidence_sha256']
        destination=exp/source.name
    destination.parent.mkdir(exist_ok=True);destination.write_bytes(compressed)
    assert destination.read_bytes()==compressed
    summary['artifacts'].append(dict(path=str(destination.relative_to(exp)),bytes=len(compressed),
        sha256=hashlib.sha256(compressed).hexdigest(),uncompressed_sha256=hashlib.sha256(raw).hexdigest()))
summary['failure_counts']={cause:sum(run['cause']==cause for run in runs) for cause in sorted({run['cause'] for run in runs},key=str)}
summary['remaining_issue']='All six remained in mapping: B candidate points were remembered, but full B boundaries and own-map routes were never completed; transport did not begin.'
# Large initial command diagnostics remain in detail; main summary stays compact.
for run in summary['runs']:
    if run['initial_check']:
        run['initial_check']={k:v for k,v in run['initial_check'].items() if k in ('passed','checks','elapsed_since_submit_s','actual_displacement_m')}
(exp/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(outcomes=summary['outcomes'],retrieval=summary['retrieval'],model=summary['model_accounting']),ensure_ascii=False))
