"""Recount finished MJWarp teacher episodes from raw evaluation/command ledgers."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys


def rows(path):
    path=Path(path)
    if path.exists():raw=path.read_bytes()
    else:raw=subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def exists(path):
    return path.exists() or Path(str(path)+'.zst').exists()


def read_bytes(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst'])


def read_json(path):
    return json.loads(read_bytes(path))


def digest(path, root, manifest):
    p=Path(path);p=p if p.exists() else Path(str(p)+'.zst')
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    if manifest.get(str(p.relative_to(root)))!=sha:
        raise ValueError('final manifest mismatch: '+str(p))
    return dict(path=str(p),sha256=sha,final_manifest_match=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--teacher-source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--groups',help='closed group IDs for a partial audit; default all7; never qualifies fewer than40 episodes')
    a=p.parse_args()
    groups=[int(x) for x in a.groups.split(',')] if a.groups else list(range(7))
    if not groups or len(set(groups))!=len(groups) or not set(groups)<=set(range(7)):
        p.error('unique group IDs0..6 required')
    spec=importlib.util.spec_from_file_location('warp3_recount_score',a.teacher_source/'sim/grasp_act_solo_evaluation.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results=[];attempts=[];reasons=Counter();kinds={};sources=set();profiles=[]
    all_groups_complete=len(groups)==7;inventory_expected=0;manifests=[]
    for group in groups:
        root=a.root/f'teacher-r1-group{group}'
        summary=read_json(root/'summary.json');sources.add(summary['source_sha'])
        if summary['status']=='running':raise RuntimeError('unfinished group: '+str(group))
        all_groups_complete &= summary['status']=='complete'
        inventory_expected+=summary['nworld']
        for rel,expected in summary['sha256'].items():
            if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=expected:
                raise ValueError('final artifact manifest mismatch: '+str(root/rel))
        manifests.append(dict(group=group,files=len(summary['sha256']),mismatch=0,
            summary_sha256=hashlib.sha256(read_bytes(root/'summary.json')).hexdigest()))
        if summary['physics_backend']!='mjwarp_batch_v1':raise ValueError('non-Warp cohort')
        if not summary.get('gate_eligible') or summary.get('gate_admission',{}).get('status')!='APPROVED_PINNED':
            raise ValueError('unapproved gate cohort')
        profiles.append({k:summary.get(k) for k in ('host','teacher_sha','numpy_teacher_v1','batch_sleep_v1',
            'native_sleep_policy_compat_v1','float32_solver_default_v1','sap_segmented_v1',
            'camera','scene_status','runtime_native_ray_kinematics_guard','plan_sha256')})
        artifact=lambda path:digest(path,root,summary['sha256'])
        for index,seed in enumerate(summary['world_seeds']):
            folder=root/f'world-{index:03d}'
            if not exists(folder/'plan.json') or not exists(folder/'result.json'):
                resource=bool(summary.get('resource_cap_end'))
                attempt=dict(group=group,world=folder.name,seed=seed,kind=None,
                    status='cap_end' if resource else 'HOST_ERROR',group_status=summary['status'],raw=str(folder),
                    error=summary.get('error') or summary.get('reason') or 'episode artifacts not created before group termination',
                    valid_teacher_episode=False,cap_end=resource,cap_scope='resource' if resource else None,
                    artifact_status='missing episode artifacts; group summary retained')
                attempts.append(attempt);reasons[attempt['error']]+=1
                continue
            plan=read_json(folder/'plan.json');result=read_json(folder/'result.json')
            if plan['seed']!=seed:raise ValueError('seed differs from frozen group inventory')
            attempt=dict(group=group,world=folder.name,seed=plan['seed'],kind=plan['kind'],status=result['status'],
                group_status=summary['status'],raw=str(folder),error=result.get('error') or summary.get('error'))
            attempt['setup_artifacts']=[artifact(folder/'plan.json'),artifact(folder/'result.json')]
            attempts.append(attempt)
            if result['status'] not in ('complete','cap_end') or 'teacher' not in result:
                attempt['cap_end']=result.get('cap_end',False)
                attempt['cap_scope']='resource' if result.get('cap_end') else None
                attempt['valid_teacher_episode']=False
                reasons[attempt['error'] or attempt['status']]+=1
                continue
            evaluation_ledger=rows(folder/'eval-only.jsonl')
            evaluation=[row for row in evaluation_ledger if 'min_z' in row]
            lookaround_views=[row for row in evaluation_ledger if row.get('kind')=='lookaround_view']
            commands=rows(folder/'teacher-commands.jsonl')
            if len(evaluation)!=len(commands):raise ValueError('unaligned command/evaluation ledger')
            score=module.Score()
            fields=('min_z','support_z','tilt_deg','finger_forces','speed','open_issued','placement_offset','weld_active')
            for ev,command in zip(evaluation,commands):
                if ev['t']!=command['t']:raise ValueError('evaluation/command clock mismatch')
                numeric=[ev[k] for k in ('t','min_z','support_z','tilt_deg','speed','placement_offset')]+ev['finger_forces']
                if not all(math.isfinite(value) for value in numeric):raise ValueError('nonfinite evaluation sample')
                score.add(ev['t'],**{k:ev[k] for k in fields})
            command_complete=any(c['phase']=='complete' for c in commands)
            physical=score.record(command_complete)
            for key in ('physical_success','lift_success','release_success'):
                if physical[key]!=result[key]:raise ValueError('raw recount disagrees with runner: '+key)
            audit=result['input_audit']
            if audit['invisible_measurements'] or audit['held_world_reads']:raise ValueError('forbidden teacher input read')
            if summary.get('runtime_native_ray_kinematics_guard') is not True:raise ValueError('missing runtime native guard')
            timed_out=result['teacher']['command_result']=='phase_timeout'
            cap=bool(result['cap_end'] or timed_out)
            attempt['valid_teacher_episode']=True
            row=dict(**attempt,**physical,cap_end=cap,runner_cap_end=result['cap_end'],
                cap_scope='phase_sim_budget' if timed_out else 'episode_sim_budget' if cap else None,
                command_complete=command_complete,
                command_result=result['teacher']['command_result'],input_audit=audit,
                failure_category=None if physical['physical_success'] else 'cap_end' if cap else
                    'lift_gate' if not physical['lift_success'] else 'release_gate' if not physical['release_success'] else 'command_incomplete',
                blocking_object='not_attributed',minimum_gap_m=None,
                minimum_gap_status='no geometric blocker attribution before playback review',
                samples=len(evaluation),lookaround_view_events=len(lookaround_views),artifacts=[artifact(folder/'eval-only.jsonl'),artifact(folder/'teacher-commands.jsonl'),artifact(folder/'result.json')])
            results.append(row);count=kinds.setdefault(plan['kind'],dict(n=0,N=0,cap_end=0))
            count['N']+=1;count['n']+=int(physical['physical_success']);count['cap_end']+=int(cap)
            if not physical['physical_success']:reasons['cap_end' if cap else row['command_result'] or 'physical_score_failed']+=1
    if len(sources)!=1:raise ValueError('mixed source cohort')
    optional=('camera','runtime_native_ray_kinematics_guard')
    base_profiles=[{k:v for k,v in profile.items() if k not in optional} for profile in profiles]
    if any(profile!=base_profiles[0] for profile in base_profiles[1:]):raise ValueError('mixed host/numeric cohort')
    cameras=[profile['camera'] for profile in profiles if profile['camera'] is not None]
    if cameras and any(camera!=cameras[0] for camera in cameras[1:]):raise ValueError('mixed camera cohort')
    attempted_seeds=[r['seed'] for r in attempts]
    if len(attempted_seeds)!=inventory_expected or len(set(attempted_seeds))!=inventory_expected:
        raise ValueError('selected attempt inventory must contain independent seeds')
    if len(groups)==7 and inventory_expected!=40:raise ValueError('full gate inventory must contain40 seeds')
    seeds=[r['seed'] for r in results]
    if len(seeds)!=len(set(seeds)):raise ValueError('replicated seeds cannot increase N')
    n=sum(r['physical_success'] for r in results);N=len(results)
    funnel=[dict(gate='selected_independent_seeds',passed=inventory_expected,rejected=0),
        dict(gate='completed_valid_ledger',passed=N,rejected=inventory_expected-N),
        dict(gate='visible_only_input_audit',passed=N,rejected=0),
        dict(gate='stable_physical_lift',passed=sum(r['lift_success'] for r in results),rejected=sum(not r['lift_success'] for r in results)),
        dict(gate='stable_setdown_after_lift',passed=sum(r['lift_success'] and r['release_success'] for r in results),
            rejected=sum(r['lift_success'] and not r['release_success'] for r in results)),
        dict(gate='command_complete_and_physical',passed=n,
            rejected=sum(r['lift_success'] and r['release_success'] and not r['command_complete'] for r in results))]
    report=dict(source_sha=next(iter(sources)),n=n,N=N,requested=40,passed=all_groups_complete and N==40 and n/N>=.95,
        minimum_independent_episodes=40,required_success_rate=.95,
        selected_groups=groups,selected_requested=inventory_expected,manifests=manifests,
        cap_end=sum(r['cap_end'] for r in results)+sum(bool(r.get('cap_end')) for r in attempts if not r['valid_teacher_episode']),
        behavior_cap_end=sum(r['cap_end'] for r in results),
        resource_cap_end=sum(bool(r.get('cap_end')) for r in attempts if not r['valid_teacher_episode']),
        HOST_ERROR=sum(not r['valid_teacher_episode'] and (r['status']=='HOST_ERROR' or r['group_status']=='HOST_ERROR') for r in attempts),
        per_kind=kinds,reasons=dict(reasons),funnel=funnel,rows=results,attempts=attempts,cohort=profiles[0],
        reproduce=['python3',str(Path(__file__).resolve()),*sys.argv[1:]],
        scope='raw own-command and GPU evaluation ledger recount; partial groups cannot qualify40 gate; playback review required separately; no C/GCP1 pooling')
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','attempts')},indent=2))


if __name__=='__main__':main()
