"""Saved-input replay and static analysis only: no simulator or rendering."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
from itertools import groupby

from harness.visual_arm_v3 import tool_pose, solve_grip_site_ik, MOUNT_X_M
from harness.grasp_act_visible_world import VisibleWorld
from sim.cargo_teacher_profile import CRATE
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.crate_lift_pose import OPTION, CARTESIAN_OPTION, elbow_torque, select_lift_prefix, THRESHOLD_NM
from sim.crate_cartesian_lift import plan_lift, static_torques
from sim.grasp_act_teacher import local, wrap, IssuedArm, grasp_poses
from sim.s2_servo_stiffness import TORQUE_NM
from scripts.zone_teacher import ArmSequence

EXP = Path(__file__).resolve().parent
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
OUT = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate8-audit')


def read(path):
    data = path.read_bytes()
    content = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else data
    return content, {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def prefixes(pwm, legacy):
    p = tool_pose(pwm)
    sink = IssuedArm(pwm); seq = ArmSequence(sink, sink.pwm)
    seq.queue(legacy, 0., duration=1.2, settle=.5)
    current = dict(sink.pwm); peak = abs(elbow_torque(current)['total_equal_share_nm']); rows = []
    for t, batch in groupby(seq.events, key=lambda e: e[0]):
        for _, sid, value in batch: current[sid] = value
        q = tool_pose(current); peak = max(peak, abs(elbow_torque(current)['total_equal_share_nm']))
        rows.append({'t': t, 'radius_mm': 1000*math.hypot(q.x_m-MOUNT_X_M, q.y_m),
                     'z_mm': q.z_m*1000, 'rise_mm': (q.z_m-p.z_m)*1000, 'peak_nm': peak})
    qualified = [x for x in rows if x['rise_mm'] >= 12]
    return {'closed_pwm': pwm, 'replayed_original_lift_pwm': legacy,
            'closed_radius_mm': math.hypot(p.x_m-MOUNT_X_M, p.y_m)*1000,
            'closed_z_mm': p.z_m*1000, 'closed_pitch_deg': p.pitch_deg,
            'closed_torque_nm': elbow_torque(pwm)['total_equal_share_nm'],
            'first_12mm_prefix': qualified[0],
            'min_peak_nm_after_12mm': min(x['peak_nm'] for x in qualified),
            'max_rise_mm_with_margin': max([0.]+[x['rise_mm'] for x in rows if x['peak_nm'] <= THRESHOLD_NM]),
            'new_plan_at_same_closed_pwm': plan_lift(pwm)[1]}


def teacher(rid, end, pwm, mode):
    return CrateGraspTeacher(rid, end, pwm, bounds=(-20, 20, -20, 20),
        teacher_stability='align_relook_v1', teacher_search='search_reacquire_v1',
        approach_goal_set='approach_goal_set_v1', crate_lift_pose=mode)


def replay(g, labels, roles, mode):
    ts = {r: teacher(r, e, labels[r][0]['applied_command']['pwm'], mode) for r,e in roles.items()}
    models = {r: VisibleWorld(r, e, profile=CRATE) for r,e in roles.items()}
    compared = 0; trace = {r: [] for r in roles}; mismatch = None
    for i, row in enumerate(g):
        now = row['t']
        inputs = {r: models[r].observe(row['visible_measurements'][r], now) for r in roles}
        for r,t in ts.items(): t.prepare_signal(inputs[r], now)
        for r,t in ts.items():
            expected = labels[r][i]; w = inputs[r]
            if w['beam'] is not None and w['visibility'][r]['visible_probes'] >= 5:
                pose, pt, heading, goal = t._geometry(w); x,y = local(pose, pt)
                try: grasp_poses((x,y,pt[2])); reachable=True
                except ValueError: reachable=False
                trace[r].append({'t':now, 'phase':t.phase, 'local_target_m':[x,y,pt[2]],
                    'goal_error_m':math.dist(pose[:2],goal), 'yaw_error_rad':wrap(heading-pose[2]),
                    'ik_reachable':reachable, 'visible_probes':w['visibility'][r]['visible_probes']})
            t.skill_started = now-expected['skill_elapsed_s']
            cmd,done=t.step(w,now,permit_pick=row['pick_permits'][r],permit_lift=row['lift_permits'][r])
            old = expected['clean_teacher_command']
            equal = (cmd['pwm'] == old['pwm'] and cmd['wheels'] == old['wheels'] and
                     all(abs(a-b) <= 1e-10 for a,b in zip(cmd['duration_s'],old['duration_s'])))
            if not equal or t.phase != expected['teacher_phase']:
                mismatch={'tick':i,'t':now,'rid':r,'phase_before':trace[r][-1]['phase'] if trace[r] else None,
                          'old_phase':expected['teacher_phase'],'new_phase':t.phase,
                          'old_command':expected['clean_teacher_command'],'new_command':cmd}
                break
            compared+=1; models[r].issue(expected['applied_command']);t.remember_applied(expected['applied_command'])
        if mismatch:break
    return {'compared_robot_ticks':compared,'N':len(g)*2,'first_divergence':mismatch,
            'comparison':'PWM/wheels/phases exact; duration tolerance 1e-10 s; conditioned on recorded applied history'},trace,ts


def audit():
    summary={'source_sha':'c5a76175086473115eacd7bef6fe662e06fd908f','physics_steps':0,'render_calls':0,
             'root_causes':{'late_infeasible_pose':5,'insufficient_clearance_with_elbow_saturation':3,
                            'approach_stall':1,'alignment_stall':1},'success_n':0,'N':10,'runs':[],
             'missing_evidence':['measured joint angles/velocities absent in all old rows',
                                 'contact vectors absent: pad normals are NOT vertical load sharing'],
             'counterfactual_scope':'Stop candidate replay at first changed command; later saved views are invalid counterfactuals.'}
    reference=json.loads(Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/crate-diag-c5a76175.json').read_text())
    expected_hashes={r['seed']:r['result_sha256'] for r in reference['rows']}
    for seed in range(77940,77950):
        p=RAW/f'crate-diag-{seed}-c5a76175'/'raw';refs=[]
        def load(name,lines=False):
            data,ref=read(p/name);refs.append(ref)
            return [json.loads(s) for s in data.splitlines()] if lines else json.loads(data)
        result=load('result.json');assert refs[-1]['sha256']==expected_hashes[seed]
        ev=load('eval-only.jsonl.zst',True);g=[e for e in ev if e['stage']=='grasp']
        labels={r:load(f'teacher-{r}.jsonl.zst',True)[:len(g)] for r in ('r1','r2')}
        _,xml_ref=read(p/'scene.xml');refs.append(xml_ref)
        roles=result['prefix']['assigned'];base,trace,teachers=replay(g,labels,roles,OPTION)
        candidate,_,_=replay(g,labels,roles,CARTESIAN_OPTION)
        assert base['first_divergence'] is None, (seed,base)
        row={'seed':seed,'raw':str(p),'sources':refs,'outcomes':result['prefix']['outcomes'],
             'input_audit':{k:result['input_audit'][k] for k in ('invisible_measurements','held_world_reads')},
             'baseline_replay':base,'candidate_replay':candidate,'closed':{},'lift_window':None}
        for r in roles:
            closed=next((l for l in labels[r] if l['teacher_phase']=='closed'),None)
            if closed:row['closed'][r]=prefixes(closed['applied_command']['pwm'],teachers[r].lift_pose)
            if seed in (77948,77949):
                row.setdefault('last_visible_geometry',{})[r]=trace[r][-1] if trace[r] else None
                row.setdefault('visible_geometry_ranges',{})[r]={
                    'last_10s_N':len([e for e in trace[r] if e['t']>=g[-1]['t']-10]),
                    'min_goal_error_m':min(e['goal_error_m'] for e in trace[r]),
                    'ik_reachable_n':sum(e['ik_reachable'] for e in trace[r]),'N':len(trace[r])}
        start=next((i for i,e in enumerate(g) if any(e['lift_permits'].values())),None)
        if start is not None:
            w=g[start:];stats={}
            for r in roles:
                stats[r]={}
                for joint in ('shoulder','elbow','wrist'):
                    values=[e['servo_load'][r][joint]*TORQUE_NM[joint] for e in w]
                    stats[r][joint]={'min_nm':min(values),'max_nm':max(values),
                        'saturated_n':sum(abs(e['servo_load'][r][joint])>=.98 for e in w),'N':len(w)}
            row['lift_window']={'t0':w[0]['t'],'end_t':w[-1]['t'],'joint_stats':stats,
                'height_min_mm':min(e['crate']['min_z'] for e in w)*1000,
                'height_max_mm':max(e['crate']['min_z'] for e in w)*1000,
                'max_tilt_deg':max(e['crate']['tilt_deg'] for e in w),
                'height_pass_n':sum(e['crate']['min_z']>=.012 for e in w),
                'contact_pass_n':sum(all(min(e['contacts'][r])>=.5 for r in roles) for e in w),
                'tilt_pass_n':sum(e['crate']['tilt_deg']<=10 for e in w),'N':len(w),
                'load_sharing':'unavailable; contacts are unsigned finger normal sums, not vertical forces',
                'time_series':[{'t_since_lift':e['t']-w[0]['t'],'height_mm':e['crate']['min_z']*1000,
                                'tilt_deg':e['crate']['tilt_deg'],'servo_load':e['servo_load'],
                                'normal_contacts_n':e['contacts']} for e in w]}
        summary['runs'].append(row)
    # Preserve the original 49-point grid, compare on the same planned closes.
    summary['radius_scan']=[]
    for i in range(49):
        radius=.146+i*.00025;hover,down=grasp_poses((MOUNT_X_M+radius,0.,.024));pwm={1:1500,**down[-1]}
        old,old_report=select_lift_prefix(pwm,hover);new,new_report=plan_lift(pwm)
        summary['radius_scan'].append({'radius_mm':radius*1000,'old':old_report['status'],'new':new_report['status']})
    summary['baseline_replayed_robot_ticks']=sum(r['baseline_replay']['compared_robot_ticks'] for r in summary['runs'])
    OUT.mkdir(parents=True,exist_ok=True)
    # Full 0.1-s evidence remains local; tracked summary links its hash.
    full=OUT/'analysis.json.zst';raw=(json.dumps(summary,indent=2)+'\n').encode()
    full.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=raw))
    assert subprocess.check_output(['zstd','-dc',str(full)])==raw
    for row in summary['runs']:
        if row['lift_window']:row['lift_window'].pop('time_series')
    summary['full_analysis']={'path':str(full),'sha256':hashlib.sha256(full.read_bytes()).hexdigest()}
    (EXP/'crate8-analysis.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
    print(json.dumps({'baseline_robot_ticks':summary['baseline_replayed_robot_ticks'],
                     'rows':[{k:r[k] for k in ('seed','last_visible_geometry','visible_geometry_ranges') if k in r} for r in summary['runs']],
                     'radius_scan':summary['radius_scan']}))


if __name__=='__main__':audit()
