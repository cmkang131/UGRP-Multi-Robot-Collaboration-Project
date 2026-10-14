"""Frozen own-detection/command replay. No physics, rendering, host or model calls.

Full precision originals are hashed before replay; truth is joined only after fit.
The new trajectory is NOT reconstructed by replaying an old trajectory's inputs.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).parent
sys.path[:0]=[str(ROOT),str(BASE)]
from analyze_release8 import read,rows,decoded,integrated,RAW
from harness.zone_final_environment import resolve
from sim.global_landmark_localization import GlobalLandmarkMatcher,PARAMS,observations,rotation,wrap
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.release_global_observation import margin_report,pair_choice

OUT=ROOT/'outputs/release9-review'
SOURCE='a7f0cdcd65142a8adf4d8bff4268423e89d4d7b0'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a,b):
    if isinstance(a,dict):return a.keys()==b.keys() and all(close(v,b[k]) for k,v in a.items())
    if isinstance(a,list):return len(a)==len(b) and all(close(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool):return abs(a-b)<1e-6
    return a==b


def fit_summary(record):
    keys=('accepted','reason','hypotheses','inliers','inlier_views','normal_rank','score','score_gap','proposed','groups')
    return dict(seed=record['seed'],rid=record['rid'],end=record['end'],fits={mode:dict(
        decision={k:v['decision'].get(k) for k in keys},evaluation=v['evaluation'],
        support=v['trace']['support'],score_quantiles=v['trace']['score_quantiles']) for mode,v in record['fits'].items()})


class TraceMatcher(GlobalLandmarkMatcher):
    """Analysis-only trace, not used for candidate generation/selection."""
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.removed_refinements=[]

    def pose_supported(self,poses):
        supported=super().pose_supported(poses)
        if len(poses)==1 and not supported[0]:self.removed_refinements.append(np.asarray(poses[0]).tolist())
        return supported


def fit(matcher,vs,cmd):
    d=matcher.fit(vs,cmd);support=copy.deepcopy(matcher.support_audit)
    fs=observations(vs,cmd);matches=[matcher.candidates(f) for f in fs]
    q=matcher.hypotheses(fs,matches);er,_=matcher.residuals(q,fs,matches)
    scores=np.maximum(0,1-er/PARAMS['inlier_sigma']**2).sum(1)
    order=np.argsort(-scores,kind='stable')
    removed=[]
    for p in matcher.removed_refinements:
        e,_=matcher.residuals(p,fs,matches)
        removed.append(dict(pose=p,score=float(np.maximum(0,1-e/6.25).sum())))
    return d,dict(support=support,score_quantiles=np.quantile(scores,[0,.25,.5,.75,.9,.99,1]).tolist(),
                  top_seeds=[dict(pose=q[i].tolist(),score=float(scores[i])) for i in order[:5]],
                  removed_refinements=removed)


def replay_actions(result,plan,fitted,labels):
    """Actual coordinator on frozen commands + fitted own poses; no truth."""
    static=resolve(plan['map_id'])[0];zone=static['regions'][plan['destination_region']]
    rect=(*zone['center_m'],*zone['half_extents_m']);reports={'off':{},'map_free_v1':{}}
    choices=result['code_decisions'][1:];max_error=0.;saved_reports={}
    for rid in ('r1','r2'):
        ts=labels[rid];teacher=ReleaseTeacher(rid,plan['roles'][rid],ts[0]['pwm'],handoff_pose_estimate=None,
            zone_rect=rect,reach_mode=result['reach_mode'],odometry_profile=result['command_motion'])
        per_robot=[x for x in fitted if x['rid']==rid]
        # A terminal coordinator break precedes the next teacher log row.
        # Its most recent issued-command state is still the frozen input.
        indices={i:min(range(len(ts)),key=lambda j:abs(ts[j]['t']-c['t'])) for i,c in enumerate(choices)}
        for index,row in enumerate(ts):
            now=row['t'];teacher.pwm={int(k):v for k,v in row['pwm'].items()}
            if teacher.holding and not row['holding_belief']:teacher.released_here(now)
            teacher.holding=row['holding_belief']
            for ci,choice in enumerate(choices):
                if index==indices[ci]:
                    decision_time=choice['t']
                    assert abs(now-decision_time)<.101
                    latest=max((x for x in per_robot if x['end']<=now+1e-6),key=lambda x:x['end'])
                    for mode in reports:
                        dec=latest['fits'][mode]['decision']
                        loc=SimpleNamespace(decision=dec,own=SimpleNamespace(x=dec.get('proposed',[0,0,0])))
                        rep=margin_report(loc,teacher,decision_time,lateral_recovery='bounded_v1')
                        reports[mode].setdefault(str(decision_time),{})[rid]=rep
                    saved=row['report'];old=reports['off'][str(decision_time)][rid]
                    assert old['kind']==saved['kind'],(rid,now,old,saved)
                    if old['kind']=='localized_margin':
                        for k in ('margin_m','lateral_clearance_m','lateral_shift_lo_m','lateral_shift_hi_m'):
                            max_error=max(max_error,abs(old[k]-saved[k]))
                            assert abs(old[k]-saved[k])<1e-6,(rid,now,k,old[k],saved[k])
                    saved_reports.setdefault(str(decision_time),{})[rid]=saved
            dt=np.clip(np.array(row['wheel_until'])-now,0,.1);duration=float(max(dt))
            if duration:teacher.dead_reckon(np.array(row['wheels'])*dt/duration,duration)
    actions=[]
    for original in choices:
        now=original['t'];old=pair_choice(saved_reports[str(now)],('r1','r2'),now,lateral_recovery='bounded_v1')
        assert old==original,(old,original)
        new=pair_choice(reports['map_free_v1'][str(now)],('r1','r2'),now,lateral_recovery='bounded_v1')
        actions.append(dict(t=now,old=old,new=new,unchanged=close(old,new),
                            new_own_reports=reports['map_free_v1'][str(now)]))
    return dict(decisions=actions,unchanged=sum(x['unchanged'] for x in actions),N=len(actions),
                old_report_max_abs_error_m=max_error,scope='Frozen trajectory only; stop causal interpretation at first changed action.')


def main():
    OUT.mkdir(exist_ok=True,parents=True);evidence={};runs=[];allfits=[];frames=[]
    for no in (0,1):
        folder=RAW/f'release8-diagnostic-{no:02d}-{SOURCE[:8]}';raw=folder/'raw'
        remote={line.split(maxsplit=1)[1].split(folder.name+'/',1)[1]:line.split()[0]
                for line in (folder/'SHA256SUMS').read_text().splitlines()}
        manifest_path=raw/('manifest.json' if (raw/'manifest.json').exists() else 'manifest.json.zst')
        manifest=read(manifest_path);present=0;missing=[]
        for rel,meta in manifest.items():
            p=raw/rel
            if not p.exists():missing.append(rel);continue
            h=digest(p);assert h==meta['sha256']==remote['raw/'+rel],p
            if meta.get('decoded_sha256'):assert hashlib.sha256(decoded(p)).hexdigest()==meta['decoded_sha256']
            evidence[str(p)]=h;present+=1
        assert digest(manifest_path)==remote['raw/'+manifest_path.name]
        evidence[str(manifest_path)]=digest(manifest_path)
        result=read(raw/'result.json.zst');plan=read(raw/'plan.json');assert result['source_sha']==SOURCE
        static=resolve(plan['map_id'])[0];fitted=[];labels={}
        for rid in ('r1','r2'):
            loc=result['lookaround_result'][rid];ts=rows(raw/f'teacher-{rid}.jsonl.zst');labels[rid]=ts
            times=np.array([x['t'] for x in ts]);cmds=integrated(ts,yaw_sign=-1)+result['handoff_estimates'][rid]
            for v in loc['localizer']['views']:
                assert np.max(abs(cmds[abs(times-v['t']).argmin()]-v['command_pose']))<1e-8
            for sweep in loc['evaluation']['sweeps']:
                end=sweep['t0']+sweep['sim_s'];vs=[v for v in loc['localizer']['views'] if v['t']<=end+1e-6]
                cmd=cmds[abs(times-end).argmin()];record=dict(seed=plan['seed'],rid=rid,end=end,command=cmd.tolist(),fits={})
                for mode in ('off','map_free_v1'):
                    m=TraceMatcher(static,localization_support=mode);d,trace=fit(m,vs,cmd)
                    record['fits'][mode]=dict(decision=d,trace=trace)
                assert record['fits']['off']['decision']['accepted']==sweep['decision']['accepted']
                # No eval labels were passed to either fit. Join them here only.
                truth=np.array(sweep['after']['truth']);record['evaluation_truth']=truth.tolist()
                for value in record['fits'].values():
                    d=value['decision'];q=np.array(d['proposed']);value['evaluation']=dict(xy_error_m=float(np.linalg.norm(q[:2]-truth[:2])),yaw_error_deg=math.degrees(float(wrap(q[2]-truth[2]))))
                record['stored_views']=len(vs);record['window_times']=[v['t'] for v in vs[-18:]]
                fitted.append(record);print(plan['seed'],rid,round(end,1),[(k,v['decision']['accepted'],round(v['evaluation']['xy_error_m'],4)) for k,v in record['fits'].items()],flush=True)
        actions=replay_actions(result,plan,fitted,labels)
        robots={rid:dict(N=len(v['localizer']['views']),nonempty=sum(bool(x['wall_points'] or x['floor_lines'] or x['doors']) for x in v['localizer']['views']),
                  detection_counts={k:sum(x[k] for x in v['localizer']['views']) for k in ('wall_points','floor_lines','doors')}) for rid,v in result['lookaround_result'].items()}
        runs.append(dict(seed=plan['seed'],run=folder.name,original_success=result['release_success'],original_outcome=result['release_outcome'],
            original_input_audit={k:result['input_audit'][k] for k in ('held_world_reads','invisible_measurements')},
            raw_manifest_present=present,raw_manifest_missing=len(missing),missing_types=sorted({Path(x).suffix for x in missing}),
            detectors=robots,active_observation=result['active_observation'],actions=actions))
        allfits.extend(fitted)
        if no==1:
            lookup={meta['sha256']:rel for rel,meta in manifest.items()}
            dest=OUT/'reviewed-originals';dest.mkdir(exist_ok=True)
            for p in sorted(Path('/private/tmp/rg8').glob('*.jpg')):
                h=digest(p)
                if h not in lookup:continue
                rel=lookup[h];assert remote['raw/'+rel]==h
                dst=dest/p.name
                if not dst.exists():shutil.copy2(p,dst)
                assert digest(dst)==h
                frames.append(dict(path=str(dst),original=rel,sha256=h,release_s=int(p.name.split('_')[1].split('-')[0])/10))
            assert len(frames)==21
    detail=dict(fits=allfits,evidence=evidence,reviewed_frames=frames)
    blob=json.dumps(detail,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
    compressed=subprocess.check_output(['zstd','-q','-c'],input=blob)
    path=BASE/'release9-analysis-detail.json.zst';path.write_bytes(compressed)
    assert subprocess.check_output(['zstd','-dc',str(path)])==blob
    summary=dict(source_sha=SOURCE,scope='Stored detector/issued-command replay, no JPEG detection replay or new physical success.',
        runs=runs,original_decisions_reproduced=len(allfits),reviewed_frames=21,reviewed_sim_times=[10.1,19.1,37.1,55.1,73.1,91.1,108.1],
        detail=dict(path=path.name,sha256=digest(path),decoded_sha256=hashlib.sha256(blob).hexdigest(),decoded_bytes=len(blob)),
        verified_present_raw_files=len(evidence),missing='Native consumed 640x480 JPEGs remain unretrieved; 21 hash-matched review JPEGs recovered locally.',
        selected_fits=[fit_summary(x) for x in allfits if x['seed']==74963 and x['rid']=='r1'],
        success_74940_original_accepted_pose_exact=sum(x['fits']['off']['decision']['accepted'] and x['fits']['off']['decision']['proposed']==x['fits']['map_free_v1']['decision']['proposed'] for x in allfits if x['seed']==74940))
    (BASE/'release9-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    assert (BASE/'release9-analysis.json').stat().st_size<65536
    print('actions',[(r['seed'],r['actions']['unchanged'],r['actions']['N']) for r in runs])


if __name__=='__main__':main()
