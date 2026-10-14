"""Replay seven saved command/detection ledgers, without physics or rendering.

Truth is joined after decisions for evaluation; never used to reconstruct inputs.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness import zone_pair_highpose_contract as contract
from sim.active_lookaround import OwnPose
from sim.global_landmark_localization import GlobalLandmarkMatcher
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.release_global_observation import margin_report,pair_choice,lateral_shift_plans
from sim.visible_belief import odometry

BASE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
SHA='14ddb6ad33b7a86ad68eee0e5c98762a8771e14c'


def main():
    evidence={};runs=[];details=[];n_decisions=0;n_reports=0;max_reconstruction_error=0.
    matcher=GlobalLandmarkMatcher(contract.resolve('zone_wide_two_doors_final_v3')[0])
    for i in range(7):
        folder=RAW/f'release-global-diagnostic-{i:02d}-{SHA[:8]}'
        manifest=dict((line.split(maxsplit=1)[1],line.split()[0]) for line in (folder/'SHA256SUMS').read_text().splitlines())
        def read(name):
            p=folder/'raw'/name
            if not p.exists():p=Path(str(p)+'.zst')
            blob=p.read_bytes();digest=hashlib.sha256(blob).hexdigest()
            remote='/home/ugrp/ugrp-sim/runs/'+str(p.relative_to(RAW))
            assert manifest[remote]==digest,(p,'hash mismatch')
            evidence[str(p.relative_to(RAW))]=digest
            return subprocess.check_output(['zstd','-dc'],input=blob) if p.suffix=='.zst' else blob
        result=json.loads(read('result.json'));plan=json.loads(read('plan.json'))
        assert result['source_sha']==SHA
        teachers={};locals_={};timelines={};estimates={}
        for rid in ('r1','r2'):
            labels=[json.loads(s) for s in read(f'teacher-{rid}.jsonl').splitlines()]
            teacher=ReleaseTeacher(rid,plan['roles'][rid],{int(k):v for k,v in labels[0]['pwm'].items()},
                handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7),reach_mode='pad_window_v2')
            cmd=OwnPose(result['handoff_estimates'][rid]);timeline=[]
            last_report=None
            for row in labels:
                now=row['t'];teacher.pwm={int(k):v for k,v in row['pwm'].items()}
                if teacher.holding and not row['holding_belief']:teacher.released_here(now)
                teacher.holding=row['holding_belief']
                saved=row['report']
                if saved and saved.get('kind')=='localized_margin' and saved!=last_report:
                    views=[v for v in result['lookaround_result'][rid]['localizer']['views'] if v['t']<=now+1e-7]
                    dec=matcher.fit(views,cmd.x)
                    assert dec['accepted']
                    loc=SimpleNamespace(own=SimpleNamespace(x=dec['proposed']),decision=dec)
                    old=margin_report(loc,teacher,now)
                    for key in ('margin_m','lateral_clearance_m'):
                        assert abs(old[key]-saved[key])<1e-7,(folder.name,rid,now,key,old[key],saved[key])
                        max_reconstruction_error=max(max_reconstruction_error,abs(old[key]-saved[key]))
                    new=margin_report(loc,teacher,now,lateral_recovery='bounded_v1')
                    # Replay identical stored scalar inputs; the map fit's
                    # cross-platform floating-point noise is measured above.
                    new={**new,**saved}
                    timeline.append(dict(t=now,old=saved,new=new,estimate=dec['proposed']))
                    n_reports+=1;last_report=saved
                    locals_[rid]=loc
                seconds=max(max(0.,min(.1,u-now)) if w else 0. for w,u in zip(row['wheels'],row['wheel_until']))
                dx,dy,da=odometry(row['wheels'],seconds);cmd.propagate(dx,dy,da)
                teacher.dead_reckon(row['wheels'],seconds)
            teachers[rid]=teacher;timelines[rid]=timeline
            estimates[rid]=timeline[-1]['estimate']
        changed=[];replayed=[]
        for original in result['code_decisions'][1:]:
            rows={rid:max((v for v in timelines[rid] if v['t']<=original['t']+1e-7),key=lambda v:v['t']) for rid in timelines}
            old=pair_choice({r:v['old'] for r,v in rows.items()},('r1','r2'),original['t'])
            assert old==original,(folder.name,old,original)
            new=pair_choice({r:v['new'] for r,v in rows.items()},('r1','r2'),original['t'],lateral_recovery='bounded_v1')
            n_decisions+=1
            if new!=old:changed.append(dict(old=old,new=new))
            replayed.append(dict(old=old,new=new))
        assert bool(changed)==(not result['release_success']),(folder.name,changed,result['release_success'])
        if changed:
            assert len(changed)==1 and changed[0]['new']['reason']=='localized_lateral_correction'
            plans=lateral_shift_plans(locals_,teachers,changed[0]['new']['lateral_shift_m'])
            assert len(plans['r1'])==len(plans['r2'])
        # Separate truth join starts here, after ALL controller decisions.
        evals=[json.loads(s) for s in read('eval-only.jsonl').splitlines()]
        evals=[e for e in evals if 'robots' in e]
        evaluation={}
        for rid in ('r1','r2'):
            final=timelines[rid][-1];e=min(evals,key=lambda v:abs(v['t']-final['t']))
            pose=final['estimate'];truth=e['robots'][rid]['pose']
            (ex,ey),(ox,oy),_=teachers[rid].end_and_outward(final['t'])
            c,s=math.cos(pose[2]),math.sin(pose[2])
            center_hat=[pose[0]+c*(ex-.3*ox)-s*(ey-.3*oy),pose[1]+s*(ex-.3*ox)+c*(ey-.3*oy)]
            b=e['beam']['pose']
            evaluation[rid]=dict(map_position_error_m=math.dist(pose[:2],truth[:2]),
                map_xy_error_m=[pose[k]-truth[k] for k in (0,1)],
                map_yaw_error_deg=math.degrees((pose[2]-truth[2]+math.pi)%(2*math.pi)-math.pi),
                estimated_center_offset_m=[center_hat[0]-4.6,center_hat[1]-.4],
                estimated_center_xy_error_m=[center_hat[k]-b[k] for k in (0,1)],
                true_lateral_envelope_clearance_m=.3-abs(b[0]-4.6)-.30*abs(math.cos(b[2]))-.02*abs(math.sin(b[2])),
                final_report=final['old'],lateral_interval_m=[final['new']['lateral_shift_lo_m'],final['new']['lateral_shift_hi_m']])
        start=min(evals,key=lambda v:v['t'])['beam']['pose'];end=evals[-1]['beam']['pose']
        run=dict(run=folder.name,seed=plan['seed'],original_success=result['release_success'],
            decisions=len(replayed),changed_decisions=changed,final_evaluation=evaluation,
            beam_start_xy=start[:2],beam_final_xy=end[:2],
            beam_displacement_m=[end[k]-start[k] for k in (0,1)],
            issued_axial_sum_m=sum(d.get('shift_m',0.) for d in result['code_decisions'] if d['action']=='shift'),
            evaluation_position_error=result['evaluation_position_error'],success_rule=result['success_rule'],
            input_audit={k:result['input_audit'][k] for k in ('invisible_measurements','held_world_reads')},
            raw_remote='/home/ugrp/ugrp-sim/runs/'+folder.name,
            status=result['status'],outcome=result['release_outcome'])
        if i in (2,6):
            files=sorted((folder/'raw/eval-overview').glob('*-release-*.jpg'))
            selected=[files[round(j*(len(files)-1)/5)] for j in range(6)]
            run['visually_reviewed_frames']=[]
            for p in selected:
                k=int(p.name.split('-')[0]);t=labels[min(k,len(labels)-1)]['t']
                for camera in ('eval-overview','eval-own/r1','eval-own/r2'):
                    name=camera+'/'+p.name;read(name)
                    run['visually_reviewed_frames'].append(dict(path=name,t=t))
        runs.append(run);details.append(dict(run=folder.name,reports=timelines,decisions=replayed))
        print(folder.name,'decisions',len(replayed),'changed',len(changed),flush=True)
    detail=BASE/'release5-replay-detail.json.zst'
    detail.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=json.dumps(dict(runs=details,files=evidence)).encode()))
    summary=dict(scope='saved command + detected-landmark replay, no RGB redetection/physics/render; no counterfactual success claim',
        original_sha=SHA,runs=runs,original_success=5,original_n=7,reports_reconstructed=n_reports,
        old_decisions_exact=n_decisions,max_report_reconstruction_error_m=max_reconstruction_error,
        success_runs_unchanged=5,failure_terminal_decisions_changed=2,
        verified_files=len(evidence),detail=dict(path=detail.name,sha256=hashlib.sha256(detail.read_bytes()).hexdigest()))
    (BASE/'release5-replay.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
