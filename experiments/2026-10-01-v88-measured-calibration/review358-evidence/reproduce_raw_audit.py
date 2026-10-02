"""Offline PR358 raw audit: JSON/XML + NumPy/SciPy only, no MuJoCo import."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path.cwd())
parser.add_argument('--raw-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--base', default='0bf41800272ec4c4bfa035cfc5609af8850e3e48')
parser.add_argument('--head', default='9b8a89c45b94264ff83708e062df04403344b7a0')
args = parser.parse_args()
ROOT = args.repo.resolve()
sys.path.insert(0, str(ROOT))
from scripts.final_pair_calibration_io import plan_arrays

STATE = {'raw_root': str(args.raw_root)}
DEST = args.output.parent
DEST.mkdir(parents=True, exist_ok=True)
if args.output.exists():
    raise FileExistsError(args.output)
MAP = 'zone_wide_two_doors_final_v3'
POSITION_TOL, ROTATION_TOL = 1e-4, 2e-3


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def delta(p1, r1, p2, r2):
    return np.max(np.abs(p1-p2), axis=-1), np.max(np.abs(r1-r2), axis=(-2, -1))


def stats(dp, dr, mask):
    p, r = dp[mask], dr[mask]
    if not len(p):
        return {'n': 0}
    joint = np.maximum(p/POSITION_TOL, r/ROTATION_TOL)
    best = int(np.argmin(joint))
    return {'n': len(p), 'pass': int(np.count_nonzero(joint <= 1)),
            'position_min_m': float(p.min()), 'rotation_min_element': float(r.min()),
            'position_max_m': float(p.max()), 'rotation_max_element': float(r.max()),
            'joint_min_normalized': float(joint.min()),
            'joint_min_pair': [float(p[best]), float(r[best])]}


def joint_addresses(xml):
    pos, vel, addresses = 0, 0, {}
    for node in xml.find('worldbody').iter():
        if node.tag not in ('joint', 'freejoint'):
            continue
        kind = node.get('type', 'free' if node.tag == 'freejoint' else 'hinge')
        addresses[node.get('name')] = (pos, vel)
        pos += {'free': 7, 'ball': 4}.get(kind, 1)
        vel += {'free': 6, 'ball': 3}.get(kind, 1)
    return addresses, pos, vel


report = {'definitions': {
    'norms': 'componentwise maximum absolute position and 3x3 rotation difference, same as np.allclose(rtol=0)',
    'active_command': 'nonzero mecanum command on the interval to the neighbouring pose sample; does not assert physical displacement',
    'stationary_command_1s': 'zero own drive commands throughout the preceding 1s and the interval to the neighbour; arm motion may exist',
    'coast_transition': 'zero interval command but a nonzero own drive command in preceding 1s',
    'neighbour_label': 'label at frame j versus pose[4*j-1] and pose[4*j+1], valid boundaries only',
    'neighbour_pose': 'pose[i] versus pose[i+1] over all 50ms intervals',
    'inverse_step': 'xyz_prev=qpos_xyz-dt*qvel_xyz; R_prev=R(qpos_quat)*Exp(-dt*qvel_local_angular)',
}, 'collections': {}}

for profile in ('unloaded', 'fine', 'loaded'):
    folder = (Path(STATE['raw_root'])/('calibration-'+profile)/MAP).resolve()
    bundle = read(folder/'bundle.json')
    xml = ET.parse(folder/'scene.xml').getroot()
    addresses, nq, nv = joint_addresses(xml)
    dt = float(xml.find('option').get('timestep'))
    trace = rows(folder/'eval_only/trajectory.jsonl')
    qp = np.asarray([r['qpos'] for r in trace])
    qv = np.asarray([r['qvel'] for r in trace])
    assert qp.shape == (7401, nq) and qv.shape == (7401, nv)
    u, spans, ticks = plan_arrays(bundle['measurement'])
    alt = {**bundle['measurement'], 'initial_hold_s': bundle['measurement']['motion_start_s']}
    u_alt, spans_alt, ticks_alt = plan_arrays(alt)
    assert np.array_equal(u, u_alt) and spans == spans_alt and ticks == ticks_alt
    rec = {'folder': str(folder), 'source_sha': bundle['source_sha'], 'timestep_s': dt,
           'initial_hold_missing': 'initial_hold_s' not in bundle['measurement'],
           'motion_start_s': bundle['measurement']['motion_start_s'],
           'fallback_equivalent': True, 'robots': {}, 'schema': {}}
    for relative in ('bundle.json','result.json','inputs/static_map.json','inputs/schedule.json','artifacts.sha256.json'):
        obj = read(folder/relative)
        rec['schema'][relative] = sorted(obj) if isinstance(obj,dict) and relative != 'artifacts.sha256.json' else sorted(obj[0]) if isinstance(obj,list) else 'relative artifact path -> SHA256'
    for relative in ('plan.json','result.json'):
        rec['schema']['../'+relative] = sorted(read(folder.parent/relative))
    for relative in ('eval_only/contacts.jsonl','eval_only/trajectory.jsonl'):
        rr = rows(folder/relative)
        rec['schema'][relative] = sorted(set().union(*(set(r) for r in rr)))
    for rid in ('r1','r2'):
        pose = rows(folder/f'eval_only/{rid}/pose.jsonl')
        label = rows(folder/f'eval_only/{rid}/camera_labels.jsonl')
        frames = rows(folder/f'robots/{rid}/frames.jsonl')
        commands = rows(folder/f'robots/{rid}/commands.jsonl')
        for name, data in [('pose',pose),('label',label),('frames',frames)]:
            rec['schema'][rid+'/'+name] = sorted(set().union(*(set(r) for r in data)))
        kinds = {}
        for row in commands:
            kinds.setdefault(row['kind'],set()).update(row)
        rec['schema'][rid+'/commands'] = {k:sorted(v) for k,v in kinds.items()}
        p = np.asarray([r['base_position_m'] for r in pose])
        rot = np.asarray([r['base_rotation'] for r in pose])
        lp = np.asarray([r['base_position_m'] for r in label])
        lr = np.asarray([r['base_rotation'] for r in label])
        tt = np.asarray([r['t'] for r in pose])
        inds = np.arange(1851)*4
        assert all('sim_time' in f and 't' not in f for f in frames)
        assert np.allclose([f['sim_time'] for f in frames], tt[inds], atol=1e-7, rtol=0)
        qa, va = addresses[rid+'__base_free']
        current_p = qp[:,qa:qa+3]
        q = qp[:,qa+3:qa+7]
        current_r = Rotation.from_quat(q[:,[1,2,3,0]]).as_matrix()
        previous_p = current_p-dt*qv[:,va:va+3]
        previous_r = current_r @ Rotation.from_rotvec(-dt*qv[:,va+3:va+6]).as_matrix()
        same_dp,same_dr = delta(lp,lr,p[inds],rot[inds])
        q_dp,q_dr = delta(lp,lr,current_p[inds],current_r[inds])
        pre_dp,pre_dr = delta(p,rot,previous_p,previous_r)
        # Reset's t0 can already be refreshed, so report it separately.
        timing = {'same_timestamp_max': [float(same_dp.max()),float(same_dr.max())],
                  'label_vs_qpos_max': [float(q_dp.max()),float(q_dr.max())],
                  'pose_vs_inverse_substep_max_excluding_t0': [float(pre_dp[1:].max()),float(pre_dr[1:].max())],
                  'pose_vs_inverse_substep_t0': [float(pre_dp[0]),float(pre_dr[0])]}
        own_u = u if rid == 'r1' else -u if profile == 'loaded' else np.zeros_like(u)
        active = np.any(own_u != 0, axis=1)
        still = np.array([not np.any(active[max(0,i-20):i+1]) for i in range(len(active))])
        dp,dr=delta(p[:-1],rot[:-1],p[1:],rot[1:])
        pose_stats = {name:stats(dp,dr,mask) for name,mask in
                      [('all',np.ones(7400,bool)),('active_command',active),('stationary_command_1s',still),('coast_transition',~active & ~still)]}
        neighbours, examples = {}, {}
        for offset in (-1,1):
            valid=(inds+offset>=0)&(inds+offset<len(p))
            li=np.flatnonzero(valid); pi=inds[valid]+offset
            interval=np.minimum(inds[valid],pi)
            dp,dr=delta(lp[li],lr[li],p[pi],rot[pi])
            masks={'all':np.ones(len(li),bool),'active_command':active[interval],
                   'stationary_command_1s':still[interval],'coast_transition':~active[interval]&~still[interval]}
            neighbours[str(offset)]={name:stats(dp,dr,mask) for name,mask in masks.items()}
            for name,mask in masks.items():
                accepted=np.flatnonzero(mask & (dp<=POSITION_TOL)&(dr<=ROTATION_TOL))
                if len(accepted):
                    # Pick the largest accepted mismatch to show a nontrivial example.
                    best=accepted[np.argmax(np.maximum(dp[accepted]/POSITION_TOL,dr[accepted]/ROTATION_TOL))]
                    examples[str(offset)+'/'+name]={'label_index':int(li[best]),'pose_index':int(pi[best]),
                        'label_t':label[li[best]]['t'],'pose_t':pose[pi[best]]['t'],
                        'position_error_m':float(dp[best]),'rotation_error_element':float(dr[best])}
        rec['robots'][rid]={'timing':timing,'pose_neighbours':pose_stats,'label_neighbours':neighbours,'accepted_examples':examples}
    report['collections'][profile]=rec

paths = ['scripts/assemble_final_pair_calibration.py','scripts/final_pair_calibration_motion.py',
         'scripts/fit_consumer_criterion_b.py','scripts/fit_unloaded_consumer.py','scripts/fit_unloaded_hammerstein.py',
         'scripts/fit_final_environment_unloaded.py','scripts/validate_consumer_criterion_b.py',
         'experiments/2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json',
         'experiments/2026-10-01-v88-measured-calibration/criterion_B_prime.json',
         'experiments/2026-10-01-final-env-v87-calibration-fit/calibration_candidate_r4.json',
         'experiments/2026-10-01-final-env-v87-calibration-fit/consumer_report_r4.json',
         'harness/rgb_execution_bundle.py','configs/simulation_workflows.json',
         'harness/zone_final_pair_contract.py','harness/zone_final_pair_excitation.py',
         'harness/zone_final_pair_calibration.py','configs/calibration/zone_final_v3_floor_light_contract.json']
report['byte_comparisons']={}
for path in paths:
    a=subprocess.check_output(['git','show',args.base+':'+path],cwd=ROOT)
    b=(ROOT/path).read_bytes()
    assert b == subprocess.check_output(['git','show',args.head+':'+path],cwd=ROOT), path
    report['byte_comparisons'][path]={'equal':a==b,'sha256':hashlib.sha256(b).hexdigest()}
report['changed_paths']=subprocess.check_output(['git','diff','--name-only',args.base+'...'+args.head],cwd=ROOT,text=True).splitlines()
report['workflows_unchanged']=not subprocess.check_output(['git','diff',args.base,args.head,'--','.github/workflows'],cwd=ROOT)
(args.output).write_text(json.dumps(report,indent=2)+'\n')
for profile,rec in report['collections'].items():
    for rid,r in rec['robots'].items():
        print(profile,rid,'TIMING',r['timing'])
        for offset,groups in r['label_neighbours'].items():
            for group in ('active_command','stationary_command_1s'):
                print(' LABEL',offset,group,groups[group])
print('report',args.output)
