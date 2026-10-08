"""s2v47 offline evidence only. Registered peer anchors are NOT live truth.

Never imported by a controller. No simulator, replay mutation or model call.
"""
import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np

from scripts.audit_s2_formal_stops import RUNS, OUTPUTS, read, rows, sha, truth_at

ENVELOPE = np.array([[-.18, -.18], [.28, -.18], [.28, .18], [-.18, .18]])


def segment_distance(point, a, b):
    point, a, b = map(lambda x: np.asarray(x, float), (point, a, b))
    d = b-a
    u = np.clip((point-a)@d/(d@d), 0, 1) if d@d else 0.
    return float(np.linalg.norm(point-a-u*d))


def polygon(pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return ENVELOPE@np.array([[c, s], [-s, c]])+pose[:2]


def separating_gap(a, b):
    """SAT separation; negative means overlap, positive is a lower bound on gap.

    This conservative 2D envelope is not the mesh, arm-height or contact test.
    """
    answer = -math.inf
    for p in (a, b):
        for edge in np.roll(p, -1, axis=0)-p:
            n = np.array([-edge[1], edge[0]])/np.linalg.norm(edge)
            x, y = a@n, b@n
            answer = max(answer, float(max(y.min()-x.max(), x.min()-y.max())))
    return answer


def peer_contacts(samples):
    found = []
    for sample in samples:
        for contact in sample['contacts']:
            a, b = (contact[k].split('__')[0] for k in ('geom1', 'geom2'))
            if a in ('r1', 'r2', 'r3') and b in ('r1', 'r2', 'r3') and a != b:
                found.append(dict(t=sample['t'], **contact))
    return found


def commanded_motion(commands):
    return [q for q in commands if q['kind'] in ('mecanum', 'drive')
            and any(q.get(k, 0) for k in ('forward', 'left', 'turn'))]


def camera_audit(raw, anchor):
    # Evaluation-only optical poses plus registered anchor. The whole envelope
    # prism is deliberately larger than the actual idle robot. No pixel labels.
    from sim.masterpi_camera_profile import scaled_camera_matrix
    k = scaled_camera_matrix(640, 480)
    lo, hi = -k[0, 2]/k[0, 0], (640-k[0, 2])/k[0, 0]
    pts = np.array(list(itertools.product([anchor[0]-.18, anchor[0]+.28],
                         [anchor[1]-.18, anchor[1]+.18], [0., .4])))
    scan, headings = [], []
    for q in rows(raw/'eval_only/camera-pose.jsonl'):
        if q['t'] > 23.85: break
        r, origin = np.array(q['camera_from_body_optical_rotation']), np.array(q['camera_from_body_xyz_m'])
        center = (np.r_[anchor[:2], .15]-origin)@r
        headings.append(dict(t=q['t'], registered_center_angle_deg=float(np.degrees(np.arctan2(center[0], center[2])))))
        if q['t'] <= 12.:
            x = (pts-origin)@r
            outside = (bool((x[:, 2] <= 0).all()) or bool((x[:, 0]-lo*x[:, 2] < 0).all())
                       or bool((x[:, 0]-hi*x[:, 2] > 0).all()))
            scan.append(dict(t=q['t'], conservative_prism_outside_horizontal_frustum=outside))
    frames = rows(raw/'robots/r3/frames.jsonl')
    selected = []
    for t in (2.25, 3.75, 5.25, 6.75, 8.25, 9.75, 11.5, 23.85):
        f = min(frames, key=lambda f: abs(f['sim_time']-t))
        selected.append(f)
    return dict(scope='evaluation only; peer registered anchor, not measured live peer pose',
        horizontal_pinhole_angles_deg=np.degrees(np.arctan([lo, hi])).tolist(),
        scan_samples=len(scan), scan_prism_outside=sum(q['conservative_prism_outside_horizontal_frustum'] for q in scan),
        scan_closest_center_angle=min((q for q in headings if q['t']<=12), key=lambda q: abs(q['registered_center_angle_deg'])),
        contact_center_angle=headings[-1], frames_to_inspect=selected)


def diagnose(seed):
    raw = OUTPUTS/RUNS[seed]
    record = read(raw/'student_record.json')
    truth = rows(raw/'eval_only/trajectory.jsonl')
    anchors = read(raw/'eval_only/setup.json')['spawns']
    hits = peer_contacts(rows(raw/'eval_only/contacts.jsonl'))
    initial = next(e for e in record['events'] if e['event']=='path')['plan']
    out = dict(seed=seed, raw=str(raw), controller_inputs=record['controller_inputs'],
        peer_actual_trajectory_available=False, peer_estimates_and_sigma_available=False,
        registered_anchor_caveat='setup positions only; passive motion unmeasured, especially after impact; never controller input',
        peer_contact_points=len(hits), peer_contact_samples=len(set(q['t'] for q in hits)),
        peer_contact_interval=[min(q['t'] for q in hits), max(q['t'] for q in hits)] if hits else None,
        contact_pairs=sorted(set(q['geom1']+' / '+q['geom2'] for q in hits)), peers={},
        first_plan=initial, registered_anchor_minima={}, timeline=[],
        source_hashes={n:sha(raw/n) for n in ('student_record.json', 'eval_only/setup.json',
                      'eval_only/trajectory.jsonl', 'eval_only/contacts.jsonl', 'eval_only/camera-pose.jsonl',
                      'robots/r1/commands.jsonl', 'robots/r2/commands.jsonl')})
    for rid in ('r1', 'r2'):
        cmds=rows(raw/f'robots/{rid}/commands.jsonl')
        peer=np.array([*anchors[rid][:2], anchors[rid][3]])
        sample=min(truth, key=lambda q: math.dist(q['robot_xyz_m'][:2], peer[:2]))
        pose=np.r_[sample['robot_xyz_m'][:2], sample['robot_yaw_rad']]
        path=initial['waypoints_m']
        out['peers'][rid]=dict(registered_anchor=peer.tolist(),commands=cmds,
            drive_commands=len(commanded_motion(cmds)), estimate=None, sigma=None,
            actual_trajectory=None, own_rgb_frames=len(list((raw/f'robots/{rid}/rgb').glob('*.jpg'))))
        out['registered_anchor_minima'][rid]=dict(t=sample['t'],
            center_distance_m=float(np.linalg.norm(pose[:2]-peer[:2])),
            envelope_separating_axis_gap_m=separating_gap(polygon(pose),polygon(peer)),
            initial_path_min_center_m=min(segment_distance(peer[:2],a,b) for a,b in zip(path,path[1:])))
    if seed==1054:
        for t in (22.35,22.65,23.10,23.85,24.10,24.60,25.05):
            p=min(record['poses'],key=lambda q:abs(q['t']-t)); gt=truth_at(truth,t)
            peer=np.array([*anchors['r1'][:2],anchors['r1'][3]])
            cmd=[q for q in record['commands'] if q['t']<=t][-1]
            out['timeline'].append(dict(t=t,r3_eval_pose=gt,r3_report={k:p[k] for k in
                ('t','t_est','x','y','yaw','std_xy_m','std_yaw_rad')},r3_last_command=cmd,
                r1_registered_anchor=peer.tolist(),r1_actual_pose=None,r1_estimate=None,r1_sigma=None,
                r1_command='no drive; initial servo only',
                estimated_distance_to_registered_anchor_m=math.dist([p['x'],p['y']],peer[:2]),
                evaluated_distance_to_registered_anchor_m=math.dist(gt[:2],peer[:2]),
                r3_report_xy_error_at_its_time_m=math.dist([p['x'],p['y']],truth_at(truth,p['t_est'])[:2])))
        q=next(q for q in record['pulse_motion_model']['transformations'] if abs(q['t']-23.85)<1e-6)
        p=next(p for p in record['poses'] if abs(p['t']-23.85)<1e-6)
        profile=record['pulse_motion_model']['model']['profiles'][q['profile_key']]
        curve=np.array(profile['mean_curve']); c,s=math.cos(p['yaw']),math.sin(p['yaw'])
        projected=curve[:,:2]@np.array([[c,s],[-s,c]])+np.array([p['x'],p['y']])
        d=np.linalg.norm(projected-np.array(anchors['r1'][:2]),axis=1)
        out['contact_pulse']=dict(selection=q,profile=profile,
            predicted_registered_anchor_min_center_m=float(d.min()),
            own_2sigma_m=2*p['std_xy_m'],peer_sigma_known=False,
            radius_sum_m=2*float(np.linalg.norm(ENVELOPE,axis=1).max()),
            criterion_lower_bound_with_peer_sigma_zero_m=2*float(np.linalg.norm(ENVELOPE,axis=1).max())+2*p['std_xy_m'])
        out['camera']=camera_audit(raw,anchors['r1'])
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=dict(version='s2v47-diagnosis-v1',controller_code_changed=False,new_physics=0,
        gt_use='evaluation only; peer live positions not recorded; anchor distances are conditional references',
        runs=[diagnose(s) for s in RUNS])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({r['seed']:dict(contact_points=r['peer_contact_points'],anchor_minima=r['registered_anchor_minima']) for r in result['runs']}))


if __name__=='__main__':main()
