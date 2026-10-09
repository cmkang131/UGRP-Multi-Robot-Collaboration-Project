"""Offline completed S2 records only: issued pulse -> body-frame displacement.

Never imported by a controller. Evaluation coordinates label calibration data,
not observations. Interpolate the 20 Hz saved trajectory; preserve raw files.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path

import numpy as np
from harness.owncam_localizer import LoadState

AXES = ('forward', 'left', 'turn')


def read(path):
    return json.loads(path.read_text())


def key(row):
    return f"{int(row['loaded'])}:{row['axis']}:{row['u']:.2f}:{row['duration_s']:.2f}"


def extract(path):
    result = read(path/'result.json')
    if result['status'] in ('RUNNING', 'running'):
        raise ValueError('completed records only')
    student = read(path/'student_record.json')
    trajectory = [json.loads(s) for s in (path/'eval_only/trajectory.jsonl').read_text().splitlines()]
    times = np.array([r['t'] for r in trajectory])
    values = np.array([[*r['robot_xyz_m'][:2], r['robot_yaw_rad']] for r in trajectory])
    values[:, 2] = np.unwrap(values[:, 2])
    def pose(t):
        return np.array([np.interp(t, times, values[:, i]) for i in range(3)])
    commands = student['commands']
    load = LoadState()
    pulses = []
    states = [e for e in student['events'] if e['event'] == 'state']
    state_t = [e['t'] for e in states]
    for command in commands:
        load.command(command)
        u = [command.get(a, 0.) for a in AXES]
        if command['kind'] not in ('drive', 'mecanum') or not any(u):
            continue
        if sum(v != 0 for v in u) != 1:
            raise ValueError('not a single-axis recorded pulse')
        axis = int(np.argmax(np.abs(u)))
        t = command['t']
        pulses.append(dict(t=t, axis=AXES[axis], u=u[axis], duration_s=command['duration_s'],
            loaded=load.loaded, state=states[max(0,bisect.bisect_right(state_t,t)-1)]['state'],
            servo=dict(load.servo)))
    for index, row in enumerate(pulses):
        t, duration = row['t'], row['duration_s']
        # Existing coarse controller waits 100 ms after native expiry. The next
        # pulse bounds a cycle; do not attribute any later command to this one.
        end = min(t+duration+.20, pulses[index+1]['t'] if index+1 < len(pulses) else times[-1])
        p = pose(t)
        c, s = np.cos(p[2]), np.sin(p[2])
        rotate = np.array([[c,s,0],[-s,c,0],[0,0,1.]])
        row.update(seed=result.get('seed',read(path/'bundle.json')['task']['seed']),
            settle_s=end-t-duration, delta=(rotate@(pose(end)-p)).tolist(),
            during_delta=(rotate@(pose(t+duration)-p)).tolist(),
            times=np.linspace(0,end-t,round((end-t)/.01)+1).tolist())
        row['curve'] = [(rotate@(pose(t+dt)-p)).tolist() for dt in row['times']]
        row['key'] = key(row)
    hashes = {f:hashlib.sha256((path/f).read_bytes()).hexdigest() for f in
              ('result.json','bundle.json','student_record.json','eval_only/trajectory.jsonl')}
    return pulses, dict(path=str(path), hashes=hashes, source_sha=result['source_sha'])


def summarize(rows):
    out = {}
    for k in sorted({r['key'] for r in rows}):
        group = [r for r in rows if r['key']==k]
        delta = np.array([r['delta'] for r in group])
        during = np.array([r['during_delta'] for r in group])
        out[k] = dict(n=len(group),seeds=sorted({r['seed'] for r in group}),
            states=sorted({r['state'] for r in group}),
            delta_quantiles=np.quantile(delta,[0,.05,.5,.95,1],axis=0).tolist(),
            delta_mean=delta.mean(0).tolist(),delta_std=delta.std(0).tolist(),
            during_median=np.median(during,axis=0).tolist(),
            distance_quantiles=np.quantile(np.linalg.norm(delta[:,:2],axis=1),[0,.05,.5,.95,1]).tolist(),
            settle_range_s=[min(r['settle_s'] for r in group),max(r['settle_s'] for r in group)])
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    rows=[];sources=[]
    for path in a.source:
        r,s=extract(path);rows.extend(r);sources.append(s)
    report=dict(scope='offline evaluation only; exploratory, not independent confirmation',
        measurement='body frame at pulse start; linear interpolation of saved 20 Hz xy/unwrapped yaw; cycle ends at min(expiry+200ms,next pulse)',
        quantiles=[0,.05,.5,.95,1],units=['m','m','rad'],sources=sources,
        absent_magnitudes_in_requested_35_to_40=[v for v in range(35,41) if not any(abs(r['u'])*100==v for r in rows)],
        groups=summarize(rows))
    (a.output/'pulse-groups.json').write_text(json.dumps(report,indent=2)+'\n')
    (a.output/'pulses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    print(json.dumps({k:dict(n=v['n'],median=v['delta_quantiles'][2],during=v['during_median']) for k,v in report['groups'].items()},indent=2))


if __name__=='__main__':main()
