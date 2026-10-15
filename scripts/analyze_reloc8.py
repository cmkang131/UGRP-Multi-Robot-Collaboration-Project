"""Saved own-camera evidence/proposal replay only. No plant/render/network.

Run from the relevant worktree with --flow carry or selfmap. GT is read only
after policy decisions, for error scoring. Selected RGB is not a full replay.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np
from harness.active_relocalization import next_view

BASE = Path('/Users/changmin/projects/ugrp/outputs')
REPORTS = BASE/'e2e18-admin/gcp-reports'


def load(path, sources):
    path = Path(path)
    if not path.exists(): path = Path(str(path)+'.zst')
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    receipt = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   decoded_sha256=hashlib.sha256(raw).hexdigest())
    # Verify original bytes, including losslessly compressed originals.
    root = next((p for p in path.parents if (p/'SHA256SUMS').exists()), None)
    if root is not None:
        hashes = {line.split()[-1].split('/'+root.name+'/', 1)[-1]:line.split()[0]
                  for line in (root/'SHA256SUMS').read_text().splitlines()}
        relative = str(path.relative_to(root))
        expected = hashes.get(relative, hashes.get(relative.removesuffix('.zst')))
        if expected is not None:
            assert expected in (receipt['sha256'], receipt['decoded_sha256']), str(path)
            receipt['original_manifest_verified'] = True
    sources.append(receipt)
    return ([json.loads(l) for l in raw.splitlines()] if '.jsonl' in path.name else json.loads(raw))


def image_metrics(path):
    """Explicit material-color proxy, not semantic segmentation or GT."""
    im = cv2.imread(str(path)); assert im is not None
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    valid = im.max(2) > 25
    # Gray checker tiles and blue checker tiles; dark blue-gray wall is separate.
    b, g, r = np.moveaxis(im.astype(float), -1, 0)
    gray = (np.abs(b-r) < 18) & (g > 74)
    blue = (b > r+23) & (b > 100)
    floor = (gray | blue) & valid
    mark = valid & (hsv[:, :, 1] > 110) & ((hsv[:, :, 0] < 90) | (hsv[:, :, 0] > 130))
    floor &= ~mark
    wall = valid & ~floor & ~mark & (b >= r+7) & (b < 110)
    grayim = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=600).detect(grayim, valid.astype(np.uint8)*255)
    lines = cv2.HoughLinesP(cv2.Canny(grayim, 40, 100), 1, np.pi/180, 30,
                            minLineLength=40, maxLineGap=8)
    N = int(valid.sum())
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        resolution=[im.shape[1],im.shape[0]],
        valid_pixels=N, floor_material_fraction=float(floor.sum()/N),
        wall_material_fraction=float(wall.sum()/N), mark_color_fraction=float(mark.sum()/N),
        unclassified_fraction=float((valid & ~floor & ~wall & ~mark).sum()/N),
        ORB_keypoints=len(orb), image_lines=0 if lines is None else len(lines))


def frame_inventory(flow):
    if flow == 'carry':
        roots = [REPORTS/'solo-carry-8c6f219c-ops']
        images = sorted({p.resolve() for r in roots for p in r.rglob('*.jpg') if p.parent.name == 'own'})
    else:
        images = sorted({p.resolve() for p in (REPORTS/'selfmap6-c8d9b6e5-ops').rglob('*.jpg')
                         if p.parent.name == 'rgb'})
    unique = {}; output = []
    for path in images:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in unique: continue
        unique[digest] = str(path); output.append(image_metrics(path))
    return output


def carry(sources):
    from sim.lookaround_localization import LookaroundLocalizer
    from harness.active_relocalization import OPTION
    raw = BASE/'gcp1-runs/solo-carry-93261-8c6f219c/raw'
    saved = load(raw/'result.json', sources)
    static = load(raw/'carry-static-map.json', sources)
    views = saved['lookaround']['localizer']['localizer']['views']
    loc = LookaroundLocalizer(static, views[0]['prior'])
    loc.rank_aware_v1 = loc.robust_recovery_v1 = True
    loc.active_relocalization = OPTION
    decisions = []
    for v in views:
        prior = np.asarray(v['prior']); P = np.diag(np.square(v['prior_sigma']))
        loc.own.x, loc.own.P = prior.copy(), P.copy()
        rec = dict(t=v['t'], pan_pulse=v['pan_pulse'])
        walls, features = v['wall_endpoints'], v['features']
        loc._grid_update(walls, features, rec)
        receipt = loc.fix_acceptance(walls, [f for f in features if f['kind']=='floor_line'],
            [f for f in features if f['kind']=='door'], prior, P)
        decisions.append(dict(t=v['t'], prior=v['prior'], sigma=v['prior_sigma'],
            walls=v['wall_points'], lines=v['floor_lines'], doors=v['doors'],
            old_accepted=v['fix_acceptance']['accepted'], old_modes=v['sensor_modes'],
            new_modes=rec['reloc8_modes'], new_acceptance=receipt,
            proposal=loc.own.x.tolist(), grid=rec['grid']))
    # All decisions above are complete before accessing GT evaluation.
    evaluation = {round(e['t'], 6): e for e in saved['lookaround']['evaluation']['views']}
    truth = {t:e['truth'] for t,e in evaluation.items()}
    for d in decisions:
        g = truth[round(d['t'], 6)]
        xy = math.dist(d['proposal'][:2], g[:2])
        yaw = abs(math.degrees((d['proposal'][2]-g[2]+math.pi)%(2*math.pi)-math.pi))
        d['evaluation_only'] = dict(proposal_xy_error_m=xy, proposal_yaw_error_deg=yaw,
            dangerous=xy > .15 or yaw > 10.)
        e=evaluation[round(d['t'],6)]
        d['evaluation_only'].update({k:e[k] for k in ('error_xy_m','error_yaw_deg',
            'camera_fk_origin_error_m','camera_fk_axis_error_deg')})
        v=next(v for v in views if v['t']==d['t'])
        c,s=math.cos(g[2]),math.sin(g[2])
        world=np.asarray(v['wall_endpoints'])@np.array([[c,s],[-s,c]])+np.asarray(g[:2])
        distances=[]
        for o in static['obstacles']:
            if o.get('kind')!='wall':continue
            center,half=np.asarray(o['center_m']),np.asarray(o['half_extents_m'])
            a,b=center-half,center+half
            corners=[a,[b[0],a[1]],b,[a[0],b[1]]]
            for p,q in zip(corners,corners[1:]+corners[:1]):
                p,q=np.asarray(p),np.asarray(q);vec=q-p
                projection=p+np.clip((world-p)@vec/(vec@vec),0,1)[:,None]*vec
                distances.append(np.linalg.norm(world-projection,axis=1))
        nearest=np.min(distances,axis=0)
        d['evaluation_only'].update(wall_endpoints_near_static_wall_n=int((nearest<=.05).sum()),
            wall_endpoints_N=len(nearest),wall_endpoint_median_error_m=float(np.median(nearest)),
            wall_endpoint_tolerance_m=.05)
    initial = decisions[0]
    nbv = next_view(static, initial['prior'], np.diag(np.square(initial['sigma'])),
        hypotheses=initial['old_modes']['hypotheses'])
    return dict(run='solo-carry-93261-8c6f219c', views_N=len(decisions),
        old_accepted_N=sum(d['old_accepted'] for d in decisions),
        new_accepted_N=sum(d['new_acceptance']['accepted'] for d in decisions),
        old_ambiguous_N=sum(d['old_modes']['ambiguous'] for d in decisions),
        new_ambiguous_N=sum(d['new_modes']['ambiguous'] for d in decisions),
        dangerous_accepted_N=sum(d['new_acceptance']['accepted'] and d['evaluation_only']['dangerous'] for d in decisions),
        decisions=decisions, first_counterfactual_view=nbv,
        limitation='fixed recorded priors and endpoint/features; not a causal trajectory or new-view RGB replay; interrupted93262/93266 lack final view ledger')


def selfmap(sources):
    from harness.selfmap6_safety import CorrectionGate
    from harness.selfmap4_geometry import observe
    from harness.self_map_landmark_sensor import Sensor
    from harness.own_map_amcl_vendor.landmarks import MapFeatures
    output=[]
    for seed in (93560, 93561):
        raw=BASE/f'gcp1-runs/selfmap6-smooth-{seed}-c8d9b6e5/raw'
        trace=load(raw/'trace.jsonl', sources); frames=load(raw/'robots/r3/frames.jsonl', sources)
        static=load(raw/'inputs/static_map.json', sources)
        gate=CorrectionGate(); admissions=[]
        for row in trace:
            a=row['correction_admission']
            if a is None: continue
            # Saved precommit receipts contain original prediction, proposal and R.
            delta=np.asarray(a['innovation']); current=np.asarray(row['pose'])
            prior=current-delta if a['accepted'] else current.copy()
            candidate=current.copy() if a['accepted'] else current+delta
            prior[2]=(prior[2]+math.pi)%(2*math.pi)-math.pi
            candidate[2]=(candidate[2]+math.pi)%(2*math.pi)-math.pi
            d=gate.consider(prior, candidate, a['predicted_covariance'], a['measurement_covariance'],
                t=row['t'],frame_id=row['frame_id'],source=a['source'],view=a['view'],evidence_ids=a['evidence_ids'])
            admissions.append(dict(t=row['t'],old_accepted=a['accepted'],new=d,candidate=candidate.tolist()))
        # Evaluation only, after the complete admission replay.
        from harness.natural_floor_slam import compose
        from harness.selfmap4_geometry import inverse
        truth=load(raw/'eval_only/trajectory.jsonl',sources)
        origin=np.array([*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']])
        truth_by_t={round(g['t'],6):g for g in truth}
        for a in admissions:
            g=truth_by_t[round(a['t'],6)]
            local=compose(inverse(origin),[*g['robot_xyz_m'][:2],g['robot_yaw_rad']])
            xy=math.dist(a['candidate'][:2],local[:2])
            yaw=abs(math.degrees((a['candidate'][2]-local[2]+math.pi)%(2*math.pi)-math.pi))
            a['evaluation_only']=dict(candidate_xy_error_m=xy,candidate_yaw_error_deg=yaw,dangerous=xy>.15 or yaw>10.)
        sensor=Sensor(MapFeatures(static).hues); detections=[]
        for f in frames:
            candidates=list((REPORTS/'selfmap6-c8d9b6e5-ops').glob(f'*{seed}*/'+f['path']))
            if not candidates: continue
            path=candidates[0]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
            servo={int(k):v for k,v in f['commanded_servo'].items()}
            obs=observe(cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB),servo,sensor)
            detections.append(dict(frame_id=f['frame_id'],path=str(path),raw_columns=obs['raw_columns'],
                fitted_columns=obs['fitted_columns'],wall_segments=len(obs['segments']),
                floor_lines=sum(x['kind']=='floor_line' for x in obs['features']),
                doors=sum(x['kind']=='door' for x in obs['features'])))
        uncertain=next((r for r in trace if 'pose_uncertain' in r['insertion_blockers']),trace[-1])
        sr=uncertain['static_registration']
        nbv=next_view(static,sr['world_pose'],sr['covariance'])
        output.append(dict(seed=seed,trace_N=len(trace),admissions=admissions, recovered_detections=detections,
            old_accepted_N=sum(a['old_accepted'] for a in admissions),new_accepted_N=sum(a['new']['accepted'] for a in admissions),
            rejected_N=sum(not a['new']['accepted'] for a in admissions),
            dangerous_accepted_N=sum(a['new']['accepted'] and a['evaluation_only']['dangerous'] for a in admissions),
            registered_N=sum(r['static_registration']['registered'] for r in trace),
            ORB={k:dict(min=min(r[k] for r in trace),median=float(np.median([r[k] for r in trace])),max=max(r[k] for r in trace))
                 for k in ('features','matches','inliers')},
            independent_axes=Counter(str(r['static_registration']['geometry'].get('independent_axis_count')) for r in trace),
            first_uncertain_t=uncertain['t'],first_uncertain_elapsed_s=uncertain['t']-trace[0]['t'],first_counterfactual_view=nbv))
    return dict(runs=output,limitation='unchanged precommit safety replay and selected RGB detection; new-view pixels and full RGB bank unavailable')


def main():
    p=argparse.ArgumentParser();p.add_argument('--flow',choices=['carry','selfmap'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();sources=[]
    value=dict(schema='ugrp.reloc8_offline.v1',flow=a.flow,policy=(carry if a.flow=='carry' else selfmap)(sources),
        sources=sources,frames=frame_inventory(a.flow),physics_calls=0,render_calls=0,model_calls=0,
        previous_results_combinable=False,frame_ratio_method='heuristic color masks; black excluded; unclassified retained; ORB/Hough are image diagnostics, not matched map landmarks')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    print(json.dumps(dict(output=str(a.output),frames=len(value['frames']))))


if __name__=='__main__':main()
