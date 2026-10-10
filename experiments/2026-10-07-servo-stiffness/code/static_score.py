"""Post-run mechanical scoring only. Never imported by physical scheduler."""
from pathlib import Path
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-camera-frame-audit/code')]
from kinematics_audit import chain
from harness.servo_camera_fk import commanded_joints
from scripts.run_wall_servo_stiffness import EXP,RAW,write,sha


def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def elevation(R):return np.degrees(np.arctan2(R[2,2],np.hypot(R[0,2],R[1,2])))
def stats(v):
    return dict(median=float(np.median(v)),abs_p95=float(np.quantile(np.abs(v),.95)),
                peak_to_peak=float(np.ptp(v)))


def score(case):
    ep=RAW/case
    result=json.loads((ep/'result.json').read_text())
    if result['status']!='RECORDED':return dict(status=result['status'],static_gate_passed=False)
    start=result['start_sim_s']
    cams={round(r['t'],6):r for r in rows(ep/'eval_only/camera.jsonl')}
    points=[]
    for r in rows(ep/'eval_only/servo.jsonl'):
        c=cams[round(r['t'],6)]
        body=np.array(c['body_rotation']).reshape(3,3)
        actual=body.T@np.array(c['camera_rotation']).reshape(3,3)@np.diag([1.,-1.,-1.])
        nominal=chain(commanded_joints(r['commands'])[1])['camera_cv'][:3,:3]
        points.append(dict(t=r['t']-start,pitch_deg=float(elevation(actual)-elevation(nominal)),
            joint_error_deg={k:float(np.degrees(j['q_rad']-j['target_rad'])) for k,j in r['joints'].items()},
            q_deg={k:float(np.degrees(j['q_rad'])) for k,j in r['joints'].items()},
            max_speed_rad_s=max(abs(j['qvel']) for j in r['joints'].values())))
    phases={}
    for phase,lo,hi in [('SEARCH',4.,6.),('HIGH',10.,12.),('hover',16.,18.),('loaded_HIGH',45.,47.)]:
        a=[r for r in points if lo-1e-8<=r['t']<hi-1e-8]
        js={k:dict(error=stats([r['joint_error_deg'][k] for r in a]),
                   position=stats([r['q_deg'][k] for r in a])) for k in ('6','5','4','3')}
        pitch=stats([r['pitch_deg'] for r in a])
        phases[phase]=dict(n=len(a),pitch=pitch,joints=js,
            passed=pitch['abs_p95']<=.3 and all(v['error']['abs_p95']<=.3 and
                v['position']['peak_to_peak']<=.3 for v in js.values()))
    tr=rows(ep/'eval_only/trajectory.jsonl')
    lift=[r for r in tr if r['t']-start>=27.]
    carry=[r for r in tr if r['t']-start>=47.]
    lifted=any(r['cyan_xyz_m'][2]>.06 for r in lift)
    retained=bool(carry) and all(r['cyan_xyz_m'][2]>.06 for r in carry)
    out=dict(status='SCORED',source_sha=result['source_sha'],phases=phases,
        static_gate_passed=all(phases[p]['passed'] for p in ('SEARCH','HIGH','hover')),
        block=dict(lifted=lifted,retained_during_carry=retained,
            max_height_m=max(r['cyan_xyz_m'][2] for r in lift),
            carry_min_height_m=min(r['cyan_xyz_m'][2] for r in carry),
            passed=lifted and retained),raw_manifest_sha256=sha(ep/'artifacts.sha256.json'))
    write(ep/'post-static-frames.json',points)
    return out


def main():
    out={case:score(case) for case in ('static-off','static-on')}
    out['static_gate_passed']=out['static-on']['static_gate_passed']
    out['loaded_qualification']=('passed' if out['static-on'].get('block',{}).get('passed') else 'not_qualified')
    write(EXP/'results/static-summary.json',out)
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
