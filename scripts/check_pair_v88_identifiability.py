"""Synthetic Hammerstein input design; NO physics or fitted calibration.

Exact integration and profiled gain/drive/stop method adapted from PR #347,
eaeaaff05553ea02c649b4db9ff82470fe6372b5. #348 motivates a static deadband before
first-order lag (tau ~0.84 s), not reuse of its unloaded fit as a loaded fit.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
from harness.zone_final_pair_excitation import design, AXES
ROOT = Path(__file__).resolve().parents[1]
INTEGRAL = 'experiments/2026-09-26-vision-loc/vision_motion.py'
RESIDUAL_FLOOR = .0001

def response(segments, dt, tau, stop_tau, deadband=0., knee=None):
    """Exact integrated velocity at sample times, vectorized over tau grid.

    As in v2, stop has a separate nuisance time constant. Sampling includes
    t=0 and the terminal coast; every command boundary lies on the sample grid.
    """
    spec = importlib.util.spec_from_file_location('measurement_v2_integral', ROOT / INTEGRAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lag_integral = module.lag_integral
    shape = np.broadcast_shapes(np.shape(tau), np.shape(stop_tau), np.shape(deadband), np.shape(knee) if knee is not None else ())
    velocity, position = np.zeros(shape), np.zeros(shape)
    rows = [position.copy()]
    for duration, command in segments:
        n = round(duration / dt)
        if abs(n * dt - duration) > 1e-8:
            raise ValueError('sample grid must include command boundaries')
        effective = (np.sign(command)*np.maximum(abs(command)-deadband, 0.) if knee is None else
                     command*np.clip((abs(command)-deadband)/(knee-deadband), 0., 1.))
        for _ in range(n):
            velocity, delta = lag_integral(velocity, effective, dt, tau if command else stop_tau)
            position = position + delta
            rows.append(position.copy())
    return np.asarray(rows)



def assess(segments, gain, tau, stop_tau, deadband, knee=None):
    def prediction(g, t, d, k=knee):
        return g*response(segments, .05, t, stop_tau, d, k)
    observed = prediction(gain, tau, deadband)
    values = [gain, tau, deadband] + ([] if knee is None else [knee])
    eps = 1e-4
    columns = []
    for i in range(len(values)):
        low, high = values.copy(), values.copy()
        low[i] *= np.exp(-eps)
        high[i] *= np.exp(eps)
        columns.append((prediction(*high)-prediction(*low))/(2*eps))
    jacobian = np.column_stack(columns)/RESIDUAL_FLOOR
    eig = np.linalg.eigvalsh(jacobian.T@jacobian)
    taus = np.unique(np.r_[np.geomspace(.1, 5., 65), tau, tau*.8, tau*1.2])
    stops = np.unique(np.r_[.03, .05, .08, .12, .2, .3, .44, 1., stop_tau])
    deadbands = np.unique(np.r_[np.linspace(0., min(.018, max(abs(u) for _,u in segments)*.8), 37),
                               deadband, deadband*.8, deadband*1.2])
    knees = [None] if knee is None else np.unique(np.r_[.024, .03, .035, .04, .05, knee, knee*.8, knee*1.2])
    td, ts = np.meshgrid(taus, stops, indexing='ij')
    best_tau = best_deadband = best_knee = float('inf')
    equivalent = []
    for d in deadbands:
        for k in knees:
            if k is not None and k <= d:
                continue
            x = response(segments, .05, td.ravel(), ts.ravel(), d, k)
            gains = observed@x/np.sum(x*x, axis=0)
            rms = np.sqrt(np.mean((x*gains-observed[:,None])**2, axis=0))
            far = np.abs(td.ravel()/tau-1) >= .199999
            best_tau = min(best_tau, float(rms[far].min()))
            if abs(d/deadband-1) >= .199999:
                best_deadband = min(best_deadband, float(rms.min()))
            if k is not None and abs(k/knee-1) >= .199999:
                best_knee = min(best_knee, float(rms.min()))
            for j in np.flatnonzero(rms <= RESIDUAL_FLOOR):
                equivalent.append([float(gains[j]),float(td.ravel()[j]),float(ts.ravel()[j]),float(d),k])
    names = ['gain','drive_tau_s','stop_tau_s','deadband'] + ([] if knee is None else ['knee'])
    ranges = {name: [min(row[i] for row in equivalent), max(row[i] for row in equivalent)]
              for i,name in enumerate(names)}
    separated = best_tau > 5*RESIDUAL_FLOOR and best_deadband > 5*RESIDUAL_FLOOR
    if knee is not None:
        separated = separated and best_knee > 5*RESIDUAL_FLOOR
    return {'model': 'subtractive_deadband_then_lag' if knee is None else 'ramp_deadband_then_lag',
            'synthetic_parameters': dict(zip(names, [gain,tau,stop_tau,deadband]+([] if knee is None else [knee]))),
            'samples': len(observed), 'sample_period_s': .05, 'samples_per_drive_tau': tau/.05,
            'step_drive_tau_ratio': 10./tau, 'residual_floor': RESIDUAL_FLOOR,
            'fisher_rank': int(np.linalg.matrix_rank(jacobian)), 'parameter_count': len(values),
            'fisher_min_eigenvalue': float(eig[0]), 'fisher_condition': float(eig[-1]/eig[0]),
            'profiled_20pct_alternative_rms': {'drive_tau': best_tau, 'deadband': best_deadband,
                                             'knee': None if knee is None else best_knee},
            'within_residual_floor': ranges, 'practically_separated': bool(separated and eig[0]>0)}


def report():
    profiles = {}
    for check in ('calibration-unloaded','calibration-fine','calibration-loaded'):
        plan = design(check)
        profiles[check] = {}
        for axis, gain, deadband in zip(AXES, (1.576,1.18,.8), (.005,.0065,.005)):
            segments = [(s['duration_s'], s['value']) for s in plan['segments'] if s['axis']==axis]
            profiles[check][axis] = assess(segments,gain,.84,.08,deadband)
        # Also test the actual pair runtime's ramp deadband family: the high
        # step reaches saturation, so gain and the knee are separately visible.
        if check == 'calibration-loaded':
            segments = [(s['duration_s'],s['value']) for s in plan['segments'] if s['axis']=='forward']
            profiles[check]['runtime_ramp'] = assess(segments,.8,.84,.08,.01,.03)
    return enrich({'status':'SYNTHETIC_DESIGN_ONLY','method_source_pr':347,'real_structure_evidence_pr':348,
            'profiles':profiles,'passed':all(r['practically_separated'] for p in profiles.values() for r in p.values()),
            'limitations':['conditional on Hammerstein structure and the stated synthetic parameters/noise floor',
                           'fine/loaded/turn values are assumptions, not measured fits',
                           'stop tau profiled as nuisance; 20 Hz does not qualify fast stopping',
                           '#348 real residual ~1.8 mm exceeds the assumed 0.1 mm floor; no real identifiability claim',
                           '#348 real PRBS residuals remain; no MEASURED_SIM product or physical acceptance']})


def enrich(result):
    """Same conditional full-path clearance calculation as #347, not safety proof."""
    from harness import zone_final_pair_contract as c
    from harness.zone_final_pair_calibration import teacher_stations
    from harness.zone_final_pair_excitation import UNLOADED_POSE
    from harness.zone_final_pair_clearance import require_clearance, clearance
    result['design_sha256'] = {}
    result['nominal_clearance'] = {}
    for check in result['profiles']:
        plan = design(check)
        result['design_sha256'][check] = c.base.digest(plan)
        static = c.resolve(plan['map_id'])[0]
        starts = teacher_stations(static) if check == 'calibration-loaded' else {'r1': UNLOADED_POSE}
        paths, gaps = [], []
        for rid, (x, y, yaw) in starts.items():
            local = []
            for axis in AXES:
                p = result['profiles'][check][axis]['synthetic_parameters']
                segments = [(plan['motion_start_s'], 0.)] + [
                    (s['duration_s'], s['value']*(-1 if rid == 'r2' else 1) if s['axis']==axis else 0.)
                    for s in plan['segments']]
                segments.append((plan['sim_cap_s']-sum(t for t,u in segments), 0.))
                local.append(p['gain']*response(segments,.05,p['drive_tau_s'],p['stop_tau_s'],p['deadband']))
            angle = yaw+(local[2][1:]+local[2][:-1])/2
            dx,dy=np.diff(local[0]),np.diff(local[1])
            delta=np.column_stack((np.cos(angle)*dx-np.sin(angle)*dy,np.sin(angle)*dx+np.cos(angle)*dy))
            xy=np.vstack(([x,y],np.cumsum(delta,axis=0)+[x,y]))
            paths.append(xy)
            gaps.extend(require_clearance(static,point,plan) for point in xy)
        if check == 'calibration-loaded':
            beam = (paths[0]+paths[1])/2
            beam_gaps = [clearance(static,point,.31) for point in beam]
            if min(beam_gaps) < .35:
                raise ValueError('nominal loaded beam wall clearance insufficient')
            gaps.extend(beam_gaps)
        result['nominal_clearance'][check] = {
            'minimum_m': min(gaps), 'sample_period_s': .05,
            'samples_per_robot': len(paths[0]),
            'scope': 'conditional Hammerstein position prediction; beam follows pair midpoint; actual substep abort remains mandatory'}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=report()
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed':result['passed'],'output':str(args.output)}))
    return int(not result['passed'])

if __name__=='__main__':
    raise SystemExit(main())
