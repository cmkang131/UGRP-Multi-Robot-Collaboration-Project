from pathlib import Path
import hashlib,json
BASE=Path('/Users/changmin/projects/ugrp/outputs')
EXP=Path('/Users/changmin/projects/ugrp-wt/ego-wall-map/experiments/2026-10-11-egomap72-fresh')
NAMES=['egomap72-fresh-92f52205','egomap72-retry-92f52205','egomap72-b-return-29c0c169']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def preserve(name):
 p=BASE/'egomap72-orchestration'/(name+'-archive.json');a=json.loads(p.read_text())
 root=BASE/'azure-runs'/name
 files=[x for x in root.rglob('*') if x.is_file()]
 for f in files:
  key=str(f.relative_to(root))
  if key not in a['inventory'] or sha(f)!=a['inventory'][key]['sha256']:raise ValueError(key)
 return dict(azure_raw='/home/ugrp/ugrp-sim/runs/'+name,arm=a['path'],arm_verified=a['verified'],
    arm_native=a['path'].replace('/home/ugrp/ugrp-sim/arm/','/home/ubuntu/ugrp-archive/runs/'),archive_kind=a.get('archive_kind','directory'),archive_sha256=a.get('archive_sha256'),
    files=len(a['inventory']),bytes=sum(x.get('bytes',0) for x in a['inventory'].values()),
    receipt_local=str(p),receipt_sha256=sha(p),mac_fetch_lite=str(root),mac_files=len(files),
    mac_bytes=sum(f.stat().st_size for f in files),mac_hash_verified=True)

def compact(r):
 return {k:r[k] for k in ('name','seed','condition','status','failure','raw','output','result_sha256','scoring_error') if k in r}

old=json.loads((EXP/'summary.json').read_text())
raw=BASE/'azure-runs'/NAMES[-1]/'data/summary.json'
new=json.loads(raw.read_text());new['status']='TERMINAL'
new['raw_summary_sha256']=sha(raw)
new['delivery_scope']=dict(tensorboard_actions=0,browser_GUI_opened=0,output='summary.json and short report',Mac_raw_media_fetched=False)
new['prior_egomap71']['host_errors']=[compact(r) for r in new['prior_egomap71']['host_errors']]
new['prior_egomap71']['block_reason']='BLOCKED_CHECKPOINT_PREFIX_MISSING'
new['prior_egomap71']['lost_inputs']='own-contacts.jsonl checkpoint prefixes and egomap68 RGB bank unavailable after Oracle x86 shutdown; prior records unchanged'
new['attempts']=[]
for name,why in zip(NAMES[:2],['Missing matplotlib (8 started, 4 cancelled before start)',
                             'Task-flow correction: full adapter included box visit; 4 partial cancelled, 8 not started']):
 d=json.loads((BASE/'azure-runs'/name/'data/summary.json').read_text())
 new['attempts'].append(dict(batch=name,reason=why,excluded_from_comparison=True,
   source_sha=d['source_sha'],host_errors=[compact(r) for r in d['host_errors']],
   preservation=preserve(name)))
new['preservation']=preserve(NAMES[-1])
arm=json.loads((BASE/'egomap72-orchestration/arm-native-verification.json').read_text())
receipt=json.loads((BASE/'egomap72-orchestration'/(NAMES[-1]+'-archive.json')).read_text())
assert arm['archive_sha256']==receipt['archive_sha256']
assert arm['inventory_canonical_sha256']==hashlib.sha256(json.dumps(receipt['inventory'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert arm['member_count']==len(receipt['inventory']) and arm['verified']
new['preservation']['arm_native_verification']=arm
new['preservation']['archive_helper_sha256']=receipt['helper_sha256']
new['preservation']['lifecycle_helper_sha256']=receipt['lifecycle_helper_sha256']
new['preservation']['coordination_lock']=receipt['lock']
assert receipt['helper_sha256']==sha(EXP/'code/archive_tar.py')
new['cleanup']=json.loads((BASE/'egomap72-orchestration/cleanup.json').read_text())
new['operational_sources']=dict(executed_launcher_source_sha='29c0c169bdfd7eff91186bb90af901393340f2a1',executed_launcher_sha256=sha(BASE/'egomap72-orchestration/launch_b_return_executed.py'),resource_governor_v1_sha256=sha(EXP/'code/resource_governor_v1.py'),resource_governor_v2_sha256=sha(EXP/'code/resource_governor.py'),collector_sha256=sha(Path(__file__)))
new['preservation']['trace_compression']=dict(files=231,saved_bytes=2346407161,sha256_verified=True,original_images_retained=True)
new['orchestration_errors']=old.get('orchestration_errors',[])
new['orchestration_errors'] += [dict(stage='final_directory_archive',status='HOST_ERROR_ARCHIVE_SWITCH',exit_code=255,reason='Own rsync archive group deliberately terminated after about 6 minutes / 1275 copied files; partial directory preserved; switched to full-member-verified tar.zst',physical_runs=0),dict(stage='tar_archive_initial_lock',status='HOST_ERROR_ARCHIVE_LOCK_BUSY',attempts=2,reason='Two attempts used an overly broad scheduled-archive global lock and were blocked. Inspection found manual archive-one uses a per-run lock; fallback now uses that same per-run lock and active-writer checks. Other locks were untouched',physical_runs=0)]
new['archive_switch']=json.loads((BASE/'egomap72-orchestration/archive-switch.json').read_text())
new['environment_repair']=old.get('environment_repair')
new['references']=old.get('references',[])
new['validation']=old.get('validation',{})
new['validation']['schedule_revision']='19 relevant tests passed on two changed test files; initial 23 tests on three files passed separately'
new['validation']['test_counts_not_added']=True
new['validation'].pop('tests',None)
new['validation']['initial_source_tests']=dict(sha='92f52205f832fe75715d12606cc04b112547e638',passed=23,files=['tests/test_own_rgb_reconfirmation.py','tests/test_egomap_fresh_pair.py','tests/test_egomap_covariance.py'])
new['validation']['frozen_source_tests']=dict(sha='29c0c169bdfd7eff91186bb90af901393340f2a1',passed=19,files=['tests/test_egomap_fresh_pair.py','tests/test_own_rgb_reconfirmation.py'])
new['validation']['terminal_audit_scope']='Configuration, initial warmup images and recorded successful receive frames only; does not override terminal physical/runtime errors'
new['scoring']=dict(B='Post-run true robot XY inside static-map zone_B rectangle',returned='Post-run true robot XY within 0.20 m of first evaluated robot XY',control_access='Evaluation is post-run only; no GT or static map supplied to controller',counts='Declaration denominator and registered/measured/completed run denominators are reported separately')
new['host_error_counts']=dict(egomap71_prior=12,egomap72_environment_attempt=12,
    egomap72_task_flow_cancelled_attempt=12,final_batch=len(new['host_errors']),
    orchestration_error_records=len(new['orchestration_errors']),
    orchestration_error_occurrences=sum(x.get('attempts',1) for x in new['orchestration_errors']))
new['terminal_runs']=sum(r['status'] not in ('RUNNING','QUEUED') for r in new['runs'])
new['physical_failures']=[{k:r.get(k) for k in ('seed','condition','status','failure','raw')} for r in new['runs'] if r['status']=='PHYSICAL_FAILURE']
new['comparison_conclusion']='On made no B/return declarations and had two runtime errors. Zero false declarations therefore does not establish improved accuracy or mission completion. Both conditions had zero valid return declarations.'
new['metric_definition']='true_B and true_return count runs with evaluation-valid declarations, not every incidental physical visit to a region.'
new['completion_definition']='RECORDED means the registered controller loop ended; it does not imply true B arrival or true return. PHYSICAL_FAILURE and HOST_ERROR are separate terminal statuses.'
new['budgets']=dict(per_run_wall_s=6000,batch_wall_s=7200,total_task_wall_s=10800,absolute_deadline_utc='2026-10-11T13:41:30Z')
new['metadata_limitations']=['Inherited bundle schedule.host_cap_s=3600 is a legacy field; actual registered signal alarm is bundle.host_alarm_s=6000 on both conditions. No timing speed comparison because CPU contention and OS pauses occurred.']
new['interpretation']='Combined-toggle DEV comparison. False declarations use evaluated declarations as denominator; physical failures and non-declaration runs remain in registered/measured run counts. No claim of isolated toggle effects or transport E2E.'
audit_path=BASE/'egomap72-orchestration/terminal-audit.json'
new['validation']['terminal_audit']=json.loads(audit_path.read_text())
new['validation']['terminal_audit_sha256']=sha(audit_path)
ledger=BASE/'egomap72-orchestration/resource-events.jsonl'
events=[json.loads(x) for x in ledger.read_text().splitlines()]
pauses={};intervals=[]
for e in events:
 if e['action']=='pause_cpu_overlap':pauses[e['name']]=e['utc_epoch']
 elif e['action'].startswith('resume') and e.get('name') in pauses:
  t=pauses.pop(e['name']);intervals.append(dict(name=e['name'],start_epoch=t,end_epoch=e['utc_epoch'],seconds=e['utc_epoch']-t))
new['resources']=dict(ledger_sha256=sha(ledger),events=events,pause_intervals=intervals,unclosed_pauses=pauses,other_processes_modified=False,priority_changed=False,overlap_detected=True,overlap_scope='Sibling reservations appeared on own CPU0-7; overlap occurred before detection. Seven own workers paused, then migrated/resumed as CPUs became available.',policy='Only own processes migrated or paused; per-run and total deadlines not extended')
new['host_error_annotations']=[dict(name=r['name'],cause='Information-gain hypothetical-grid cloning loses the covariance proxy odometry pose; active_information_gain.py:44 via egomap_covariance.py:75') for r in new['host_errors'] if (r.get('failure') or {}).get('message')=='pose']
new['host_error_annotations'] += [dict(name=r['name'],cause='Render executor future.result(timeout=30.0), multi_masterpi_production.py:886; CPU contention and SIGSTOP pause are recorded potential contributors, not separately established causes') for r in new['host_errors'] if (r.get('failure') or {}).get('type')=='TimeoutError' and not (r.get('failure') or {}).get('message')]
new['remaining_issues']=[dict(issue='CovarianceView forecast clone initializes owner/driver but not base; pose delegation fails',source='harness/active_information_gain.py:97 and harness/egomap_covariance.py:73',scope='Observed on-condition runtime error; no within-cohort fix or rerun'),dict(issue='Renderer wall timeout with CPU contention/OS pause',source='sim/multi_masterpi_production.py:886',scope='Preserved HOST_ERROR; pause causality not isolated'),dict(issue='Zero observed declarations is not proof of accurate arrival/return',scope='Use declaration and run denominators; report incomplete/failed runs') ]
new['references'] += [dict(url='https://docs.python.org/3/library/os.html#os.sched_setaffinity',scope='CPU affinity only, no process priority change'),dict(url='https://docs.python.org/3/library/tarfile.html',scope='Streaming archive fallback; every ARM member verified against source SHA256 inventory if used')]
(EXP/'summary.json').write_text(json.dumps(new,indent=2,ensure_ascii=False)+'\n')
print('summary_bytes',(EXP/'summary.json').stat().st_size)
