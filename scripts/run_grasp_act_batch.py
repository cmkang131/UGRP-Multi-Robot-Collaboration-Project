"""Finite machine-bound teacher waves with a speed gate and five-minute ledger."""
from __future__ import annotations
import argparse,hashlib,json,os,signal,subprocess,sys,time
from collections import Counter
from pathlib import Path
from scripts.azure_speed_gate import verdict,SpeedWarning,kill_group,write,positive
from scripts.grasp_act_host import identity,require_run_root,same_machine,measured_speed_baseline


def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def execution_tree(source):
    # Each remote source is intentionally a single shallow commit; compare
    # the two existing trees, never assume the earlier commit is in this .git.
    raw=subprocess.check_output(['git','ls-tree','-r','HEAD','--',
        'harness','sim','scripts','configs','maps'],cwd=source,text=True)
    return {line.split('\t',1)[1]:line.split('\t',1)[0] for line in raw.splitlines()}


def reuse_speed_gate(prior,plan,concurrency,limit,execution_host,teacher_stability="off",teacher_search="off",approach_goal_set="off",nominal_blocked_handoff="off"):
    """Reuse an observed gate only when all execution code is byte-identical.

    The batch driver may change for explicit start indices. No teacher,
    actuator, contract, scene, physics, map or other execution change is allowed.
    """
    source=Path(__file__).resolve().parents[1]
    meta=read(prior/'RUN_META.json');old=meta['sha']
    baseline=prior.parents[1]/'src'/old
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip()!=old:
        raise ValueError('baseline source SHA mismatch')
    before_tree,after_tree=execution_tree(baseline),execution_tree(source)
    changed=sorted(n for n in before_tree.keys()|after_tree.keys() if before_tree.get(n)!=after_tree.get(n))
    if set(changed)-{'scripts/run_grasp_act_batch.py'}:
        raise ValueError('speed reuse requires byte-identical execution components')
    admission=read(prior/'resource-admission.json')
    same_machine(admission.get('execution_host'),execution_host)
    if admission.get('teacher_stability','off')!=teacher_stability:raise ValueError('speed gate stability mode mismatch')
    if admission.get('teacher_search','off')!=teacher_search:raise ValueError('speed gate search mode mismatch')
    if admission.get('approach_goal_set','off')!=approach_goal_set:raise ValueError('speed gate approach mode mismatch')
    if admission.get('nominal_blocked_handoff','off')!=nominal_blocked_handoff:raise ValueError('speed gate nominal handoff mode mismatch')
    if admission.get('plan_sha256')!=hashlib.sha256(plan.read_bytes()).hexdigest():
        raise ValueError('same frozen plan required')
    gate=read(prior/'speed-gate.json')
    if not gate.get('admitted') or gate.get('completed')!=concurrency or gate.get('median_wall_per_sim',float('inf'))>limit:
        raise ValueError('completed same-concurrency speed gate required')
    components={}
    for name in ('sim/grasp_act_teacher.py','sim/grasp_act_scene.py','sim/grasp_act_port.py',
                 'scripts/run_grasp_act_teacher.py','scripts/zone_teacher.py','harness/grasp_act_contract.py',
                 'harness/visual_arm_v3.py','sim/masterpi_drive_friction_v7.py','configs/simulation_workflows.json'):
        before=(baseline/name).read_bytes()
        after=(source/name).read_bytes()
        if before!=after:raise ValueError('execution bytes differ: '+name)
        components[name]=hashlib.sha256(after).hexdigest()
    proof={'prior':str(prior),'execution_baseline_sha':old,'changed_execution_files':changed,
           'identical_components_sha256':components,
           'speed_gate_sha256':hashlib.sha256((prior/'speed-gate.json').read_bytes()).hexdigest()}
    return gate,proof


def handoff_only(result):
    """Map handoff and its cancelled peers, with no independent failure."""
    failed=[t.get('outcome') for t in result.get('teachers',{}).values() if t.get('outcome')!='success']
    return any(o in ('search_timeout_handoff','approach_blocked_handoff') for o in failed) and all(o in ('search_timeout_handoff','peer_search_handoff','approach_blocked_handoff','peer_approach_handoff') for o in failed)


class FailureStop:
    """Count independent episodes, not robots or repeated supervisor polls.

    Reuse one instance across cohort waves so a shared defect cannot hide at
    a wave boundary. Clean map handoffs are terminal outcomes, not failures.
    """
    def __init__(self, scope='first_failure'):
        if scope not in ('first_failure','repeated_cause_v1'):
            raise ValueError('unknown failure stop scope')
        self.scope=scope;self.seen=set();self.causes={}

    def observe(self,index,result):
        if (index in self.seen or result.get('status')!='complete'
                or result.get('physical_success') is not False or handoff_only(result)):
            return self.triggered
        self.seen.add(index)
        ignored={'success','search_timeout_handoff','peer_search_handoff',
                 'approach_blocked_handoff','peer_approach_handoff'}
        causes={(t.get('outcome') or 'physical_success_false',t.get('phase') or 'unknown')
                for t in result.get('teachers',{}).values() if t.get('outcome') not in ignored}
        if not causes:causes={('physical_success_false',result.get('phase') or 'unknown')}
        for cause in causes:self.causes.setdefault(cause,set()).add(index)
        return self.triggered

    @property
    def triggered(self):
        minimum=2 if self.scope=='repeated_cause_v1' else 1
        return any(len(indices)>=minimum for indices in self.causes.values())

    def diagnostic(self):
        return {'scope':self.scope,'minimum_episodes':2 if self.scope=='repeated_cause_v1' else 1,
                'causes':[{'reason':reason,'phase':phase,'episode_indices':sorted(indices),'N':len(indices)}
                          for (reason,phase),indices in sorted(self.causes.items())]}


def summarize(rows,planned):
    completed=[r for r in rows if r.get('status')=='complete' and r.get('exit',0)==0]
    handoffs=[r for r in completed if handoff_only(r)]
    return {'object_kind':'long_beam','n':sum(r.get('physical_success') is True for r in completed),
        'N':len(completed),'planned_N':planned,'started_N':len(rows),
        'joint_held_n':sum(r.get('joint_held') is True for r in completed),
        'approach_handoff_n':sum(bool(r.get('approach_handoff')) for r in completed),
        'approach_handoff_rate':sum(bool(r.get('approach_handoff')) for r in completed)/len(completed) if completed else None,
        'approach_handoff_indices':[r.get('index') for r in completed if r.get('approach_handoff')],
        'clean_handoff_n':len(handoffs),'clean_handoff_rate':len(handoffs)/len(completed) if completed else None,
        'clean_handoff_indices':[r.get('index') for r in handoffs],
        'search_handoff_n':sum(bool(r.get('search_handoff')) for r in completed),
        'search_handoff_rate':sum(bool(r.get('search_handoff')) for r in completed)/len(completed) if completed else None,
        'search_handoff_indices':[r.get('index') for r in completed if r.get('search_handoff')],
        'robots':{rid:{'n':sum(r.get('teachers',{}).get(rid,{}).get('outcome')=='success' for r in completed),
            'N':len(completed)} for rid in ('r1','r2')},
        'failure_reasons':dict(Counter(t['outcome'] for r in completed for t in r.get('teachers',{}).values() if t.get('outcome')!='success')),
        'host_errors':sum(r.get('status')=='HOST_ERROR' or (r.get('status')!='interrupted' and r.get('exit',0) not in (0,-2,130)) for r in rows),
        'interrupted':sum(r.get('status')=='interrupted' or r.get('exit') in (-2,130) for r in rows),'rows':rows}


def wave(root,plan,indices,cap,*,probe,limit,complete_frozen_cohort=False,teacher_profile="legacy",execution_host='azure',teacher_stability='off',teacher_search='off',approach_goal_set='off',nominal_blocked_handoff='off',failure_stop=None):
    jobs=[];reason=None;rows=[];monitored=0.;started=time.monotonic()
    failure_stop=FailureStop() if failure_stop is None else failure_stop
    if complete_frozen_cohort and failure_stop.scope!='first_failure':
        raise ValueError('complete-frozen-cohort cannot bypass repeated-cause stopping')
    parent=read(root.parents[0]/'RUN_META.json')
    env={**os.environ,**{k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','LP_NUM_THREADS')}}
    try:
        for index in indices:
            target=root/f'episode-{index:03d}';target.mkdir(parents=True,exist_ok=False)
            write(target/'RUN_META.json',{**parent,'class':'dev','pr':484,'purpose':'speed_probe' if probe else 'teacher_gate'})
            command=[sys.executable,'-m','scripts.sim_cli','workflow','run','grasp-act-teacher','--',
                '--plan',str(plan),'--episode',str(index),'--out',str(target/'raw'),'--cap-s',str(cap),
                '--teacher-profile',teacher_profile,'--execution-host',execution_host,
                '--teacher-stability',teacher_stability,'--teacher-search',teacher_search,'--approach-goal-set',approach_goal_set,'--nominal-blocked-handoff',nominal_blocked_handoff]
            if probe:command.append('--probe')
            log=(target/'log.txt').open('x');at=time.monotonic()
            proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            write(target/'PROCESS.json',{'pid':proc.pid,'command':command,'started_unix':time.time()})
            jobs.append((index,target,proc,log,at,SpeedWarning(limit)))
        while True:
            now=time.monotonic();states=[]
            for index,target,proc,_,at,warning in jobs:
                code=proc.poll()
                result=read(target/'raw/result.json');progress=read(target/'raw/progress.json')
                states.append({'index':index,'exit':code,'progress':progress,'status':result.get('status')})
                if code not in (None,0):reason='CHILD_HOST_ERROR';break
                if not probe and not complete_frozen_cohort and failure_stop.observe(index,result):
                    reason='PHYSICAL_TEACHER_FAILURE';break
                if code is None and now-at > (max(300.,30*limit*3) if probe else max(600.,cap*limit*3)):
                    reason='WALL_TIMEOUT';break
                if code is None:
                    value=warning.observe(now,float(progress.get('sim_s',0.)))
                    if value:write(target/'SPEED_GATE_WARNING.json',value)
            if now-monitored>=300 or reason:
                write(root/f'monitor-{int(now-started):06d}.json',{'unix':time.time(),'loadavg':os.getloadavg(),'states':states,'stop_reason':reason})
                monitored=now
            if reason:break
            # Inspect the final result even when every child exited between polls.
            if all(s['exit'] is not None for s in states):break
            time.sleep(2)
    except BaseException as error:
        reason=type(error).__name__+':'+str(error)
    finally:
        if reason:write(root/'SUPERVISOR_STOP.json',{'reason':reason,'unix':time.time(),'scope':'this teacher wave only','failure_stop':failure_stop.diagnostic()})
        for _,target,proc,_,_,_ in jobs:
            # A physical result is written before compression/finalization.
            # Preserve completed failures too: interrupting this finalizer
            # would incorrectly remove the trigger failure from the denominator.
            if read(target/'raw/result.json').get('status')!='complete':kill_group(proc)
        for index,target,proc,log,at,_ in jobs:
            try:code=proc.wait(timeout=45)
            except subprocess.TimeoutExpired:kill_group(proc,signal.SIGKILL);code=proc.wait()
            log.close();(target/'EXIT').write_text(str(code)+'\n')
            result=read(target/'raw/result.json') or {'status':'HOST_ERROR','error':'missing result'}
            # Preserve each standard workflow record as well as the raw episode.
            from scripts.remote_run_finish import collect
            collect(Path(__file__).resolve().parents[1],target)
            result.update(index=index,exit=code,raw=str(target/'raw'))
            if (target/'raw/result.json').is_file():result['result_sha256']=hashlib.sha256((target/'raw/result.json').read_bytes()).hexdigest()
            rows.append(result)
    write(root/'wave.json',{'reason':reason,'rows':rows,'failure_stop':failure_stop.diagnostic()})
    return rows,reason


def selected_indices(size,start,explicit):
    if explicit is None:return list(range(start,size))
    if start!=0:raise ValueError('use start-index or episode-indices, not both')
    if not explicit or len(set(explicit))!=len(explicit) or any(i<0 or i>=size for i in explicit):
        raise ValueError('distinct frozen episode indices in range required')
    return sorted(explicit)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--concurrency',type=int,default=16);p.add_argument('--speed-gate-limit',type=positive)
    p.add_argument('--execution-host',choices=('azure','gcp1'),default='azure')
    p.add_argument('--speed-baseline',type=Path,help='same-machine concurrency measurement before the first GCP cohort')
    p.add_argument('--cap-s',type=float,default=60.);p.add_argument('--probe-only',action='store_true')
    p.add_argument('--diagnostic-only',action='store_true',help='one finite wave of seen cases; never qualifies a gate')
    p.add_argument('--start-index',type=int,default=0);p.add_argument('--speed-gate-from',type=Path)
    p.add_argument('--episode-indices',type=int,nargs='+',help='explicit unchanged frozen-plan indices; never resample')
    p.add_argument('--teacher-profile',choices=('legacy','pi_geometry_v1','observable_v2','visible_only'),default='legacy')
    p.add_argument('--teacher-stability',choices=('off','align_relook_v1'),default='off')
    p.add_argument('--teacher-search',choices=('off','search_body_scan_v1','search_body_scan_v2'),default='off')
    p.add_argument('--approach-goal-set',choices=('off','approach_goal_set_v1'),default='off')
    p.add_argument('--nominal-blocked-handoff',choices=('off','nominal_blocked_handoff_v1'),default='off')
    p.add_argument('--failure-stop-scope',choices=('first_failure','repeated_cause_v1'),default='first_failure',
        help='opt-in: stop the batch after the same reason and phase fail in two independent episodes')
    p.add_argument('--complete-frozen-cohort',action='store_true',help='record individual finite failures; operator still stops diagnosed shared defects')
    a=p.parse_args()
    failure_stop=FailureStop(a.failure_stop_scope)
    if a.complete_frozen_cohort and a.failure_stop_scope!='first_failure':
        raise ValueError('complete-frozen-cohort cannot bypass repeated-cause stopping')
    if a.teacher_stability!='off' and a.teacher_profile!='visible_only':raise ValueError('stability mode requires visible_only')
    if a.teacher_search!='off' and a.teacher_stability=='off':raise ValueError('search mode requires teacher stability')
    if a.approach_goal_set!='off' and (a.teacher_profile!='visible_only' or a.teacher_stability=='off'):raise ValueError('approach goal set requires visible_only and align_relook_v1')
    if a.nominal_blocked_handoff!='off' and (a.teacher_profile!='visible_only' or a.teacher_stability=='off'):raise ValueError('nominal blocked handoff requires visible_only and align_relook_v1')
    root=a.root.resolve();require_run_root(root);host=identity(a.execution_host)
    if a.speed_gate_limit is None:
        if a.execution_host=='gcp1':raise ValueError('GCP requires an explicit measured speed limit; Azure default cannot transfer')
        a.speed_gate_limit=3.5
    plan=a.plan.resolve();plan_data=read(plan);episodes=plan_data['episodes']
    if not 1<=a.concurrency<=16 or len(episodes)<a.concurrency:raise ValueError('explicit 1..16 concurrency and enough plans required')
    if not 0<a.cap_s<=180:raise ValueError('finite simulation cap required')
    if not 0<=a.start_index<len(episodes):raise ValueError('start index outside frozen plan')
    indices=selected_indices(len(episodes),a.start_index,a.episode_indices)
    baseline=None
    if a.execution_host=='gcp1' and not (a.probe_only or a.diagnostic_only):
        previous=a.speed_baseline or a.speed_gate_from
        if previous is None:raise ValueError('measure GCP speed with --probe-only before starting a cohort')
        baseline=measured_speed_baseline(previous,host,a.concurrency)
    load_limit=.8*host['cpu_count']
    if os.getloadavg()[0]>=load_limit:raise ValueError('HOST_LOAD_ADMISSION')
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
    if available<6*1024**2+a.concurrency*512*1024:raise ValueError('HOST_MEMORY_ADMISSION')
    write(root/'resource-admission.json',{'loadavg':os.getloadavg(),'memory_available_kib':available,
        'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'concurrency':a.concurrency,
        'episode_indices':indices,'complete_frozen_cohort':a.complete_frozen_cohort,'failure_stop_scope':a.failure_stop_scope,
        'teacher_stability':a.teacher_stability,'teacher_search':a.teacher_search,'approach_goal_set':a.approach_goal_set,'nominal_blocked_handoff':a.nominal_blocked_handoff,
        'start_nominal_goal_feasible':plan_data.get('start_nominal_goal_feasible','off'),'nominal_goal_filter':plan_data.get('nominal_goal_filter'),'execution_host':host,'load_limit':load_limit,'speed_limit':a.speed_gate_limit,'speed_baseline':baseline})
    if a.diagnostic_only:
        if len(indices)>a.concurrency or a.probe_only or a.speed_gate_from:
            raise ValueError('diagnostic is one finite wave, separate from speed and qualification')
        rows,reason=wave(root/'diagnostic',plan,indices,a.cap_s,probe=False,limit=a.speed_gate_limit,
            failure_stop=failure_stop,
            teacher_profile=a.teacher_profile,complete_frozen_cohort=a.complete_frozen_cohort,execution_host=a.execution_host,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff)
        write(root/'diagnostic.json',{**summarize(rows,len(indices)),'qualified':False,
            'purpose':'seen regression replay; not a fresh teacher gate','stop_reason':reason,'execution_host':host,'failure_stop':failure_stop.diagnostic()})
        return
    if a.speed_gate_from:
        gate,proof=reuse_speed_gate(a.speed_gate_from.resolve(),plan,a.concurrency,a.speed_gate_limit,host,a.teacher_stability,a.teacher_search,a.approach_goal_set,a.nominal_blocked_handoff)
        write(root/'execution-continuity.json',proof)
    else:
        rows,reason=wave(root/'speed',plan,range(a.concurrency),30.,probe=True,limit=a.speed_gate_limit,teacher_profile=a.teacher_profile,execution_host=a.execution_host,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff,failure_stop=failure_stop)
        samples=[{'sim_s':r.get('sim_s'),'wall_s':r.get('wall_s'),'exit':r['exit'],
            'expected_stop':r.get('status')=='complete' and r.get('sim_s',0)>=30-1e-6,
            'finalization_complete':any((Path(r['raw'])/name).is_file() for name in ('manifest.json','manifest.json.zst')),'finalization_errors':[],
            'raw':r['raw']} for r in rows]
        gate=verdict(samples,a.concurrency,a.speed_gate_limit)
        if reason:gate.update(status='SPEED_GATE_FAIL',admitted=False,reason=reason)
    write(root/'speed-gate.json',gate)
    if not gate['admitted'] or a.probe_only:return
    all_rows=[]
    for offset in range(0,len(indices),a.concurrency):
        batch=indices[offset:offset+a.concurrency]
        rows,reason=wave(root/f'cohort-{batch[0]:03d}',plan,batch,a.cap_s,probe=False,limit=a.speed_gate_limit,
            failure_stop=failure_stop,
            complete_frozen_cohort=a.complete_frozen_cohort,teacher_profile=a.teacher_profile,execution_host=a.execution_host,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff)
        all_rows.extend(rows)
        summary=summarize(all_rows,len(episodes))
        summary.update(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            failure_stop=failure_stop.diagnostic(),stop_reason=reason,
            teacher_profile=a.teacher_profile,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff,
            start_nominal_goal_feasible=plan_data.get('start_nominal_goal_feasible','off'),nominal_goal_filter=plan_data.get('nominal_goal_filter'),plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),execution_host=host,
            self_pose_source='issued',criteria=({'min_z_m':.012,'max_tilt_deg':10.,'hold_s':3.} if a.teacher_profile=='visible_only' else {'min_z_m':.012,'hold_s':1.}),
            qualified=reason is None and summary['N']>=40 and summary['n']/max(1,summary['N'])>=.95)
        write(root/'teacher-gate.json',summary)
        if reason:break


if __name__=='__main__':main()
