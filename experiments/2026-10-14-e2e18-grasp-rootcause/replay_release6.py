"""Verified saved-ledger decisions and original 80 detection cases; no backend.

New views have no saved pixels and are NEVER synthesized. Ground truth is
joined only after decisions to explain the old failure, not to plan actions.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness import zone_pair_highpose_contract as contract
from harness.zone_final_environment import resolve, digest as map_digest
from sim.global_landmark_localization import GlobalLandmarkMatcher, PARAMS
from sim.lookaround_localization import LookaroundLocalizer
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.release_global_observation import pair_choice, recovery_round

BASE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
SHA='e96386d319fee37cbf109867f55a1b9aefac4229'


def main():
    evidence={};runs=[];details=[];exact=0;diagnostic_maps={}
    # The seven new runs used the door-geometry map. Keep the older 80-case
    # reference map separate so its previously reported 77/80 is comparable.
    reference_static=contract.resolve('zone_wide_two_doors_final_v3')[0]
    reference_matcher=GlobalLandmarkMatcher(reference_static)
    def verified(folder,name):
        path=folder/'raw'/name
        if not path.exists():path=Path(str(path)+'.zst')
        manifest=dict((s.split(maxsplit=1)[1],s.split()[0]) for s in (folder/'SHA256SUMS').read_text().splitlines())
        blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
        remote='/home/ugrp/ugrp-sim/runs/'+str(path.relative_to(RAW))
        assert manifest[remote]==digest
        evidence[str(path.relative_to(RAW))]=digest
        return subprocess.check_output(['zstd','-dc'],input=blob) if path.suffix=='.zst' else blob
    for i in range(7):
        folder=RAW/f'release5-diagnostic-{i:02d}-{SHA[:8]}'
        result=json.loads(verified(folder,'result.json'));plan=json.loads(verified(folder,'plan.json'))
        scene=json.loads(verified(folder,'scene.json'))
        static=resolve(plan['map_id'])[0]
        assert map_digest(static)==scene['static_map_sha256']
        diagnostic_maps[static['map_id']]=dict(sha256=map_digest(static),verified_against_scene_manifest=True)
        matcher=GlobalLandmarkMatcher(static)
        assert result['source_sha']==SHA and result['status']=='complete'
        assert result['input_audit']['invisible_measurements']==result['input_audit']['held_world_reads']==0
        labels={r:[json.loads(s) for s in verified(folder,f'teacher-{r}.jsonl').splitlines()] for r in ('r1','r2')}
        locs={};teachers={};fitrows=[]
        for rid,item in result['lookaround_result'].items():
            saved=item['localizer'];loc=LookaroundLocalizer(static,saved['command_pose'],
                mode='setdown_global_v1',map_pose_known=saved['map_pose_known'])
            loc.views=saved['views'];loc.decision=saved['decision'];locs[rid]=loc
            teachers[rid]=ReleaseTeacher(rid,plan['roles'][rid],
                {int(k):v for k,v in labels[rid][-1]['pwm'].items()},
                handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7),reach_mode='pad_window_v2')
            teachers[rid].holding=False
            if plan['seed']==74940:
                for sweep in item['evaluation']['sweeps']:
                    end=sweep['t0']+sweep['sim_s']
                    views=[v for v in saved['views'] if v['t']<=end+1e-7]
                    # Return-to-heading command frame, as at finalize().
                    dec=matcher.fit(views,saved['command_pose'])
                    fitrows.append(dict(robot=rid,t=end,views=len(views),window_views=min(len(views),PARAMS['max_views']),
                        detections={k:sum(v.get(k,0) for v in views[-PARAMS['max_views']:])
                                    for k in ('wall_points','floor_lines','doors')},
                        replay=dec,saved=sweep['decision']))
                for view in saved['views']:
                    assert hashlib.sha256(verified(folder,view['input_jpeg'])).hexdigest()==view['input_sha256']
        before=copy.deepcopy({r:loc.decision for r,loc in locs.items()})
        changed=[];checks=[]
        for original in result['code_decisions'][1:]:
            now=original['t']
            rows={rid:max((v for v in ls if v['t']<=now+1e-7 and v['report']),key=lambda v:v['t'])['report']
                  for rid,ls in labels.items()}
            old=pair_choice(rows,('r1','r2'),now,lateral_recovery='bounded_v1')
            assert old==original,(folder.name,old,original)
            exact+=1
            if old['action']=='observe':
                # Old stages are saved control receipts, not truth labels.
                stages={r:max([0]+[a['stage'] for a in result['active_observation']
                                   if a['robot']==r and a['t']<now-1e-7]) for r in locs}
                off,_=recovery_round(locs,teachers,rows,stages.copy(),now)
                on,entries=recovery_round(locs,teachers,rows,stages.copy(),now,
                    active_recovery='map_nbv_v1',nbv_history={r:[] for r in locs})
                if off is None and on is not None:
                    changed.append(dict(t=now,old='active_observation_exhausted',new=entries,
                                        steps=on,pair_choice_unchanged=old))
                else:
                    assert on==off,(folder.name,'pre-exhaustion behavior changed')
                checks.append(dict(t=now,stages=stages,legacy_exhausted=off is None,nbv_added=on is not None and off is None))
        assert {r:loc.decision for r,loc in locs.items()}==before
        assert not changed if result['release_success'] else len(changed)==1
        runs.append(dict(seed=plan['seed'],raw=str(folder),old_success=result['release_success'],
                         pair_decisions=len(result['code_decisions'])-1,success_decisions_unchanged=not changed,
                         terminal_observation_changed=bool(changed),new_physical_success='unmeasured'))
        details.append(dict(run=folder.name,observation_checks=checks,changed=changed,localization=fitrows,
                            old_final_decisions=before,
                            evaluation_only={r:d['evaluation']['after'] for r,d in result['lookaround_result'].items()}))
    original80=[];actual_maps80=[]
    for i in range(40):
        folder=RAW/f'release-command-gate-{i:02d}-cdace35e'
        result=json.loads(verified(folder,'result.json'))
        plan=json.loads(verified(folder,'plan.json'));scene=json.loads(verified(folder,'scene.json'))
        own_static=resolve(plan['map_id'])[0]
        assert map_digest(own_static)==scene['static_map_sha256']
        own_matcher=GlobalLandmarkMatcher(own_static)
        for rid,item in result['lookaround_result'].items():
            saved=item['localizer'];dec=reference_matcher.fit(saved['views'],saved['final_estimate'])
            original80.append(dict(run=folder.name,robot=rid,decision=dec))
            actual=own_matcher.fit(saved['views'],saved['final_estimate'])
            actual_maps80.append(dict(run=folder.name,robot=rid,map_id=own_static['map_id'],decision=actual))
    frames=json.loads((ROOT/'outputs/release6-review/frames.json').read_text())
    for row in frames:
        path=Path(row['path'])
        # Discover the run root rather than depending on the view subdirectory.
        folder=next(p for p in path.parents if p.name.startswith('release5-diagnostic-'))
        assert hashlib.sha256(verified(folder,str(path.relative_to(folder/'raw')))).hexdigest()==row['sha256']
    full=dict(runs=details,original80=original80,actual_maps80=actual_maps80,files=evidence,frames_directly_reviewed=frames)
    detail=BASE/'release6-replay-detail.json.zst'
    detail.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=json.dumps(full,ensure_ascii=False).encode()))
    summary=dict(scope='offline stored scalar decisions + saved detections; no new RGB, physics, render or model calls',
        source_parent=SHA,runs=runs,replayed_pair_decisions_exact=exact,baseline_success=6,success_runs_unchanged=6,
        diagnostic_maps=diagnostic_maps,
        terminal_failure_recovery_changed=1,original80=dict(n=80,accepted=sum(r['decision']['accepted'] for r in original80),
        reasons=dict(Counter(r['decision']['reason'] for r in original80)),
        map_id=reference_static['map_id'],map_sha256=map_digest(reference_static),
        comparison='same map and detections as the previously reported 77/80 reference replay'),
        actual_maps80=dict(n=80,accepted=sum(r['decision']['accepted'] for r in actual_maps80),
            reasons=dict(Counter(r['decision']['reason'] for r in actual_maps80)),
            map_case_counts=dict(Counter(r['map_id'] for r in actual_maps80)),
            comparison='separate audit using each original plan map, verified against its scene manifest; not pooled with the fixed-reference 77/80'),
        input_audit=dict(runs=7,invisible_measurements=0,held_world_reads=0),
        visually_reviewed=dict(frames=21,time_scope='prefix start through final release-await_observe; see detail for paths/hashes'),
        evidence=dict(verified_files=len(evidence),detail=detail.name,sha256=hashlib.sha256(detail.read_bytes()).hexdigest()),
        new_physical_success='unmeasured; proposed camera views have no saved pixels',
        acceptance_params_unchanged=PARAMS,
        source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
            'sim/global_landmark_localization.py','sim/release_nbv_observation.py',
            'sim/release_global_observation.py','scripts/run_grasp_act_release.py')})
    (BASE/'release6-replay.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
