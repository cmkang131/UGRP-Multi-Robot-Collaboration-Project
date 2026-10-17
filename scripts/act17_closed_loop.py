"""Counterfactual audit of saved student states; no physics or student inputs.

CPU kinematics/rays reconstruct the frozen seven-probe camera test. A frozen
visible-only oracle is queried ONLY before its original potential-hold boundary.
Unavailable expert labels remain unavailable; never borrow a teacher's action
from a different trajectory. Exit is geometric probe exit, not pixel recognition.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from act17_open_loop import read
from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
T = B/'src/warp1-teacher-snapshot-6f057f7e'


def completed_v7_groups(root):
    """Only closed registered jobs; never mistake partial output for a failure."""
    root=Path(root);summary=read(root/'summary.json')
    if (summary.get('cohort')!='act17-v7-native' or not summary.get('complete')
            or summary.get('status')!='complete' or not summary.get('finished')):
        raise ValueError('complete registered v7 evaluation batch required')
    groups=[];seen=set()
    for job in summary['finished']:
        out=Path(job['out']).resolve()
        if (job['returncode'] or out.parent.parent!=root.resolve() or out.name!='evaluation'
                or out in seen):raise ValueError('closed unique local evaluation jobs required')
        seen.add(out);result=read(out/'summary.json');plans=read(out.parent/'plans.json')['episodes']
        if (not result.get('complete') or result.get('status') not in ['complete','cap_end']
                or result.get('cohort')!='act17-v7-native' or len(plans)!=len(result.get('student_scores',[]))):
            raise ValueError('fully observed native per-world outcomes required')
        for plan,row in zip(plans,result['student_scores']):
            if row['seed']!=plan['seed'] or row['candidate'] not in job['candidates']:
                raise ValueError('per-world candidate/seed assignment differs')
        groups.append(out.parent)
    return groups


def command_yaw_deg(command):
    # Exact frozen visible-world issued-command odometry. It predicts command
    # motion; it does not claim measured body yaw or actuator execution.
    from harness.grasp_act_visible_world import command_delta
    return math.degrees(command_delta(command, .1)[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--v7-root',type=Path,help='closed ACT17 VAL/FINAL batch; analyze failed worlds only')
    args = parser.parse_args()
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    sys.path.insert(0, str(Q/'scripts'))
    sys.path.insert(0, str(T))
    import sim
    sim.__path__.append(str(Q/'sim'))
    import mujoco
    import cv2
    from scripts.audit_grasp_act_visibility import BandVisibility
    from simalt_compiled_compat import apply_geometry
    from act16w_oracle import VisibleOracle
    args.out.mkdir(parents=True, exist_ok=False)
    exp = B/'runs/act16w-native-experiment-r1'
    rows, raw = [], {}
    totals = Counter()
    from gzip import open as gzopen
    with gzopen(args.out/'frames.jsonl.gz', 'xt') as stream:
        roots=([(None,args.v7_root)] if args.v7_root else
               [(a,exp/f'validation-{a}/validation') for a in ('A','B','C','D1')]+[('FINAL_A',exp/'final40')])
        for arm,root in roots:
            for group in completed_v7_groups(root) if args.v7_root else sorted(root.glob('group-*')):
                launched=read(group/'launch.json');launch=launched.get('args') or launched['argv']
                references_path = Path(launch[launch.index('--references')+1])
                references = read(references_path)
                raw[str(references_path)] = sha256(references_path)
                evaluation = group/'evaluation'
                plans = read(group/'plans.json')['episodes']
                actions = read(evaluation/'actor-actions.jsonl', lines=True)
                observations = read(evaluation/'actor-inputs.jsonl', lines=True)
                camera = read(evaluation/'owner/RUN_META.json')['camera']
                outcomes=read(evaluation/'summary.json')['student_scores'] if args.v7_root else None
                for wi,plan in enumerate(plans):
                    if outcomes is not None and outcomes[wi]['task_success']:continue
                    current_arm=outcomes[wi]['candidate'] if outcomes is not None else arm
                    folder = evaluation/f'owner/world-{wi:03d}'
                    xml = folder/'scene.xml'
                    model = mujoco.MjModel.from_xml_string(xml.read_text())
                    reference = references[sha256(xml)]
                    apply_geometry(model, xml, Path(reference['geometry']))
                    data = mujoco.MjData(model)
                    cid = model.camera('r1__robot_cam').id
                    model.cam_pos[cid],model.cam_quat[cid] = camera['mount_pos'],camera['mount_quat']
                    vis = BandVisibility.__new__(BandVisibility)
                    vis.np,vis.model,vis.body_gids = np,model,{}
                    vis.K,vis.D = np.asarray(camera['K']),np.asarray(camera['D'])
                    vis.groups = np.array([1,1,1,1,0,0],dtype=np.uint8)
                    vis.near = float(model.vis.map.znear*model.stat.extent)
                    vis.cameras = {'r1':cid}
                    bid = model.body('r1__robot').id
                    def robot():
                        return SimpleNamespace(base_xyz=lambda:data.xpos[bid].copy(),
                            base_rpy=lambda:(0.,0.,math.atan2(data.xmat[bid,3],data.xmat[bid,0])))
                    world = SimpleNamespace(model=model, data=data, robot=lambda rid:robot())
                    current = [r['observation'] for r in observations if r['world']==wi]
                    if not current:
                        raise ValueError('missing saved actor observations')
                    owner = SimpleNamespace(contexts=[dict(world=world,gids=vis._body_geoms(model.body('cargo_'+plan['item_id']).id))],
                        plans=[plan],previous=[current[0]['issued'][-1]], active=[True],
                        read_actor=lambda i:(owner.observation,None))
                    owner.observation = current[0]
                    oracle = VisibleOracle(owner,0)
                    eyes = SimpleNamespace(region_visible=lambda i,gids:vis.region_visible(data,'r1',gids))
                    with np.load(folder/'states.npz') as archive:
                        ticks,qpos = archive['ticks'].copy(),archive['qpos'].copy()
                    poses = {int(t):q for t,q in zip(ticks,qpos)}
                    timeline = []
                    for tick,obs in enumerate(current):
                        if tick not in poses:
                            raise ValueError('cannot substitute unsaved state')
                        data.qpos[:] = poses[tick]
                        mujoco.mj_kinematics(model,data)
                        mujoco.mj_camlight(model,data)
                        gids = owner.contexts[0]['gids']
                        points = []
                        for gid in gids:
                            points.append(data.geom_xpos[gid].copy())
                            for axis in range(3):
                                for sign in (-1,1):
                                    points.append(data.geom_xpos[gid]+sign*.8*model.geom_size[gid,axis]*data.geom_xmat[gid].reshape(3,3)[:,axis])
                        optical=(np.asarray(points)-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3)*[1,-1,-1]
                        uv=optical[:,:2]/np.maximum(optical[:,2,None],1e-12)*np.diag(vis.K)[:2]+vis.K[:2,2]
                        distorted,_=cv2.fisheye.projectPoints(optical.reshape(-1,1,3),np.zeros(3),np.zeros(3),vis.K,vis.D)
                        distorted=distorted.reshape(-1,2)
                        inside=(optical[:,2]>vis.near)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(distorted[:,0]>=0)&(distorted[:,0]<640)&(distorted[:,1]>=0)&(distorted[:,1]<480)
                        selected=actions[tick]['actions'][wi]['command']
                        owner.observation=obs
                        label=oracle.query(eyes,selected)
                        command=label.get('teacher_command')
                        value=dict(arm=current_arm,seed=plan['seed'],tick=tick,elapsed_SIM_s=tick*.1,skill=obs['skill'],
                            in_frame_probes=int(inside.sum()),probe_N=len(points),
                            student_yaw_command_deg=command_yaw_deg(selected),student_command=selected,
                            teacher_command=command,teacher_label_valid=bool(label.get('label_valid')),
                            teacher_yaw_command_deg=command_yaw_deg(command) if command else None,
                            teacher_rejection=label.get('rejection_category'),teacher_phase=label['teacher_phase'],
                            target_visible_for_teacher=label.get('target_visible'),
                            potential_hold_boundary=bool(label.get('query_blocked_by_hold_boundary')))
                        timeline.append(value)
                        stream.write(json.dumps(value)+'\n')
                    seen=False
                    exit_tick=None
                    for value in timeline:
                        if value['in_frame_probes']:
                            seen=True
                        elif seen:
                            exit_tick=value['tick'];break
                    # User requested the preceding one SIM second (10 recorded
                    # 0.1s intervals); no detection/acceptance constant is tuned.
                    window=timeline[max(0,exit_tick-10):exit_tick] if exit_tick is not None else []
                    valid=[v for v in window if v['teacher_label_valid']]
                    yaw=[v['student_yaw_command_deg'] for v in window]
                    nonzero=[math.copysign(1,x) for x in yaw if x!=0]
                    switches=sum(x!=y for x,y in zip(nonzero,nonzero[1:]))
                    comparison=Counter('opposite' if v['student_yaw_command_deg']*v['teacher_yaw_command_deg']<0 else
                        'student_stopped_teacher_turns' if v['student_yaw_command_deg']==0 and v['teacher_yaw_command_deg']!=0 else
                        'same_sign_or_teacher_stopped' for v in valid)
                    category=('no_geometric_exit' if exit_tick is None else 'oscillation' if switches else
                        'stopped_rotation' if not nonzero else 'opposite_to_available_teacher' if comparison['opposite'] else
                        'unidirectional_teacher_unavailable' if not valid else 'unidirectional')
                    row=dict(arm=current_arm,seed=plan['seed'],assigned_item_id=plan['item_id'],samples=len(timeline),
                        geometric_exit_SIM_s=exit_tick*.1 if exit_tick is not None else None,
                        exit_skill=timeline[exit_tick]['skill'] if exit_tick is not None else None,
                        pre_exit_one_second=window,valid_teacher_comparisons=len(valid),comparison=dict(comparison),
                        yaw_sign_switches=switches,reason_category=category,blocked_object='not_attributed_by_geometric_FOV_audit',
                        minimum_gap_m=None,minimum_gap_status='not_measured_FOV_not_blockage',
                        oracle_audit=oracle.audit.record(),oracle_labels=sum(v['teacher_label_valid'] for v in timeline),
                        hold_rejected=sum(v['potential_hold_boundary'] for v in timeline),
                        cap_end=bool(read(folder/'result.json').get('cap_end',False)),raw=str(folder))
                    rows.append(row);totals[category]+=1
                    for path in (xml,folder/'states.npz',group/'plans.json',evaluation/'actor-actions.jsonl',evaluation/'actor-inputs.jsonl'):
                        actual=path if path.exists() else Path(str(path)+'.zst')
                        raw[str(actual)]=sha256(actual)
                    (args.out/'progress.json').write_text(json.dumps(dict(completed=len(rows),latest_seed=plan['seed'])))
    report=dict(schema='ugrp.act17.saved_closed_loop.v1',status='complete',complete=True,source_sha=source,host=host,
        rows=rows,reason_distribution=dict(totals),physics_steps=0,training_steps=0,rendered_frames=0,
        teacher_actions_executed=0,student_inputs_changed=False,
        cohort='act17-v7-native' if args.v7_root else 'historical_act16w_v4_native',
        caveats=['CPU seven-probe/FOV reconstruction on saved MJWarp poses; not native per-pixel segmentation',
                 'Original pre-hover oracle scope and potential-hold exclusion retained; missing teacher labels are not imputed',
                 'Geometric screen exit during grasp can be expected occlusion and is not itself a causal failure'],
        funnel=[dict(gate='saved_failed_evaluations',passed=len(rows),rejected=0),
                dict(gate='screen_exit_with_expert_label_in_preceding_second',passed=sum(r['valid_teacher_comparisons']>0 for r in rows),
                     rejected=sum(r['valid_teacher_comparisons']==0 for r in rows))],
        raw=[dict(path=k,sha256=v) for k,v in raw.items()],reproduce=sys.argv)
    (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='complete',N=len(rows),reasons=dict(totals))))


if __name__ == '__main__':
    main()
