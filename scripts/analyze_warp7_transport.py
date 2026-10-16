"""gcp2 raw recount. Evaluation labels/poses never return to controllers."""
import argparse,collections,hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np


def read(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst'])


def obj(path):return json.loads(read(path))
def rows(path):return [json.loads(s) for s in read(path).splitlines()]
def dist(values):
    return dict(N=len(values),p50=float(np.percentile(values,50)) if values else None,p95=float(np.percentile(values,95)) if values else None,max=max(values) if values else None)


def analyze(root,out):
    from sim.grasp_act_solo_evaluation import ZoneScore
    from scripts.probe_scene_tex2 import write
    out.mkdir(parents=True,exist_ok=False);q=obj(root/'queue.json');batch=obj(root/'summary.json')
    manifest=obj(root/'SHA256SUMS.json')
    bad=[n for n,h in manifest.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
    reports=[];funnel=[]
    for i,t in enumerate(q['runs']):
        raw=root/f'world-{i:03d}'/'raw';item=dict(world=i,seed=t['seed'],condition=t['condition'],replica=t.get('replica',0),raw=str(raw))
        try:
            d=obj(raw/'result.json');ev=rows(raw/'eval-only.jsonl');commands=rows(raw/'teacher-commands.jsonl')
            static=obj(raw/'carry-static-map.json');plan=obj(raw/'plan.json')
            score=ZoneScore(static['regions']['zone_'+plan['destination_zone']],active_recovery=plan.get('carry5_profile')=='carry5_active_localization_v1')
            for e in ev:
                score.add(e['t'],phase=e['evaluation_phase'],footprint_xy=e['footprint_xy'],finger_contacts=e['finger_contacts'],
                    **{k:e[k] for k in ('min_z','support_z','tilt_deg','finger_forces','speed','open_issued','placement_offset','weld_active')})
            complete=d.get('teacher',{}).get('command_result')=='command_complete'
            scoring=score.record(complete);carry=d.get('teacher',{}).get('carry',{})
            xy=[e['map_pose_error_xy_m'] for e in ev if e.get('map_pose_error_xy_m') is not None]
            yaw=[abs(math.degrees(e['map_pose_error_yaw_rad'])) for e in ev if e.get('map_pose_error_yaw_rad') is not None]
            phase=collections.Counter(x.get('phase_before',x['phase']) for x in commands)
            navigation=carry.get('reloc21_progress') or {};motion=carry.get('reloc20_motion') or {}
            destination=carry.get('destination_visual_acquire') or {}
            termination=d.get('termination_reason') or d.get('error') or d['status']
            category='HOST_ERROR' if d['status'] in ('HOST_ERROR','interrupted') or batch['status']=='HOST_ERROR' else 'cap_end' if termination in ('sim_cap','phase_timeout','sim_time_cap','cap_end') else termination
            item.update(status=d['status'],termination=termination,termination_category=category,raw_recount=scoring,
                scoring_matches_report=all(scoring[k]==d.get(k) for k in ('lift_success','zone_placement_success','physical_success')),
                command_complete=complete,phase_counts=dict(phase),xy_m=dist(xy),yaw_deg=dist(yaw),
                first_t=ev[0]['t'] if ev else None,last_t=ev[-1]['t'] if ev else None,eval_samples=len(ev),commands=len(commands),
                input_audit=d.get('input_audit'),route_plan_funnel=motion.get('footprint',{}).get('plan_funnel'),
                rejections=motion.get('footprint',{}).get('rejections',[]),destination=destination,
                removal_counts=navigation.get('cumulative'),removal_events=[e for e in navigation.get('events',[]) if e.get('event') in ('candidate_rejected','selection_no_route')],
                source_result_sha256=hashlib.sha256(read(raw/'result.json')).hexdigest(),
                referee_decoded_sha256=hashlib.sha256(read(raw/'eval-only.jsonl')).hexdigest())
            stages=[('controller_commands',bool(commands)),('GPU_advanced',len(ev)>1 and ev[-1]['t']>ev[0]['t']),
                ('lifted',scoring['lift_success']),('carry',scoring['carry_samples']>0),
                ('destination_observed',destination.get('acquired_t') is not None),('placed',scoring['zone_placement_success']),('complete',scoring['physical_success'])]
            alive=True;ff=[]
            for name,passed in stages:
                rejected=alive and not passed;alive=alive and passed
                ff.append(dict(stage=name,cumulative_pass_n=int(alive),rejected_n=int(rejected)))
            funnel.append(dict(world=i,condition=t['condition'],replica=t.get('replica',0),stages=ff))
        except (FileNotFoundError,KeyError,ValueError,subprocess.CalledProcessError) as e:
            item.update(status='INCOMPLETE_ARTIFACT',termination_category='HOST_ERROR',reason=str(e),
                blocked_object='raw_result_or_referee',minimum_gap_m=None,gap_scope='artifact_not_physical_gap')
        reports.append(item)
    arms={}
    for condition in sorted({t['condition'] for t in q['runs']}):
        rr=[r for r in reports if r['condition']==condition and not r['replica']]
        eligible=[r for r in rr if r.get('termination_category')!='HOST_ERROR']
        arms[condition]=dict(attempted=len(rr),eligible=len(eligible),HOST_ERROR=sum(r.get('termination_category')=='HOST_ERROR' for r in rr),
            cap_end=sum(r.get('termination_category')=='cap_end' for r in rr),
            place=sum(r.get('raw_recount',{}).get('zone_placement_success',False) for r in eligible),
            complete=sum(r.get('raw_recount',{}).get('physical_success',False) for r in eligible))
    write(out/'runs.json',reports)
    write(out/'rejection-table.json',dict(unit='world; replica separated',runs=funnel,raw=str(root),
        source_queue_sha256=hashlib.sha256((root/'queue.json').read_bytes()).hexdigest(),
        rejections=[dict(category='HOST_ERROR',reason=e['reason'],blocked_object=e['blocked_object'],minimum_gap_m=e['minimum_gap_m']) for e in batch.get('errors',[])],
        reproduction=['python','-m','scripts.analyze_warp7_transport','--input',str(root),'--output',str(out)]))
    summary=dict(status='MEASURED' if batch['status']=='COMPLETE' and not bad else 'NOT_READY',source_sha=q['source_sha'],
        physics_host=batch['host'],analysis_host=platform.node(),pool_with_cpu=False,arms=arms,replica_worlds=sum(bool(r['replica']) for r in reports),
        verified_files=len(manifest),hash_mismatches=bad,batch_status=batch['status'],runs_file=str(out/'runs.json'),
        scorer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),raw=str(root),rejection_table=str(out/'rejection-table.json'))
    write(out/'summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 CPU analysis only')
    analyze(a.input.resolve(),a.output.resolve())
