"""Freeze prior mapbuild4 MJWarp pulse distributions, not current-run truth."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def make(vision, base, output):
    sys.path[:0]=[str(vision),str(vision/'scripts')]
    import numpy as np
    from scripts.probe_scene_tex2 import build_model
    from scripts.generate_scene_textures import MAPS
    from harness.e2e_rgb_vo import between
    from mapbuild2_capture import quaternion_heading
    m,*_=build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    pose=lambda q:np.r_[q[adr:adr+2],quaternion_heading(q[adr+3:adr+7])]
    curves={};sources=[]
    for name,onset in [('pulse-warp-r1',100),('phase-warp-r2',200)]:
        root=base/name
        meta=json.loads((root/'metrics.json').read_text());q=np.load(root/'eval-state.npz')['qpos']
        for i,row in enumerate(meta):
            if row['pose']!='drive':continue
            key=f"drive:{row['axis']}:{row['u']:.2f}:{row['ms']/1000:.2f}"
            start=pose(q[onset,i])
            curve=np.array([between(start,pose(v)) for v in q[onset:,i]])
            curves.setdefault(key,[]).append(curve)
        sources += [dict(path=str(root/n),sha256=hashlib.sha256((root/n).read_bytes()).hexdigest())
                    for n in ('metrics.json','eval-state.npz','summary.json')]
    profiles={}
    for key,rows in curves.items():
        data=np.stack(rows);mean=data.mean(0);residual=data[:,-1]-mean[-1]
        # Empirical context spread, population second moment. Two contexts are
        # not independent repeats or a calibrated 95% confidence distribution.
        cov=residual.T@residual/len(rows)
        profiles[key]=dict(times=(np.arange(len(mean))/100).tolist(),curve=mean.tolist(),
                           covariance=cov.tolist(),contexts=len(rows),
                           endpoint_samples=data[:,-1].tolist(),covariance_scope='cold/warm context spread; not repeatability')
    result=dict(physics_backend='mjwarp',contact_profile='baseline_noslip10',profiles=profiles,sources=sources,
                qualification='EXPLORATORY_CONTEXT_SPREAD_NOT_GENERALIZED',
                mean_source='mapbuild4 saved 100Hz physical MJWarp response, cold and after-forward where available',
                noise_source='empirical endpoint context covariance + OpenSLAM c716f019 motionmodel.cpp25-35, ROS defaults')
    if output.exists():raise ValueError('NO_CALIBRATION_OVERWRITE')
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output),profiles=len(profiles),sha256=hashlib.sha256(output.read_bytes()).hexdigest())))


def command_intervals(frames, commands, calibration):
    """Own issued commands + frozen old measurements, no live labels.

    Curve and context covariance share the measured one-second pulse+tail
    horizon. Covariance is allocated once over that horizon, as in the frozen
    PulseOdometry time-fraction rule, plus the standard GMapping motion noise.
    """
    import numpy as np
    from harness.mapbuild_motion import PulsePrediction, OPTION
    from harness.rbpf_rejection import motion_variance
    prediction=PulsePrediction(calibration,option=OPTION)
    index=0;active=None;last=0.;out={}
    for frame in frames:
        t=frame['t'];cov=np.zeros((3,3))
        # At 10Hz all commanded onsets lie on exact sample boundaries. Issue
        # after advancing to its time, so future commands cannot affect motion.
        delta=prediction.advance(t)
        if active:
            start,p=active;horizon=p['times'][-1]
            fraction=max(0.,min(t-start,horizon)-max(0.,min(last-start,horizon)))/horizon
            cov=np.asarray(p['covariance'])*fraction
        cov+=np.diag(motion_variance(delta))
        out[frame['frame_id']]=(delta,cov);last=t
        while index<len(commands) and commands[index]['t']<=t:
            row=commands[index]
            if row['t']!=t:raise ValueError('COMMAND_ONSET_MUST_BE_FRAME_BOUNDARY')
            prediction.issue(row);active=(t,calibration['profiles'][f"drive:{row['axis']}:{row['value']:.2f}:{row['duration_s']:.2f}"])
            index+=1
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('vision','base','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();make(a.vision,a.base,a.output)
