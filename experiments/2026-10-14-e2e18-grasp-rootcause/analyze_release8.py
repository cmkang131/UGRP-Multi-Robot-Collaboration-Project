"""Read-only evidence analysis: no simulator construction, rendering or policy truth.

Run with the existing Mac environment. Writes only derived local evidence.
360 degree visibility is an optimistic static-map calculation, not detection.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.zone_final_environment import resolve, digest
from harness.static_keepouts import keepout_rects, rect_distance
from sim.lookaround_localization import Camera, LOOK_ARM, LOOK_ARM_V2, look_servo, map_landmarks, wall_rects, _segment_hits_rect
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D
from sim.global_landmark_localization import rotation, wrap
from sim.visible_belief import odometry

BASE = Path(__file__).parent
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def decoded(p):
    if not p.exists() and p.suffix == '.zst':
        p = p.with_suffix('')
    return subprocess.check_output(['zstd', '-dc', str(p)]) if p.suffix == '.zst' else p.read_bytes()


def read(p):
    return json.loads(decoded(p))


def rows(p):
    return [json.loads(s) for s in decoded(p).splitlines()]


def stats(values):
    a = np.asarray(values, float)
    return dict(n=len(a), min=float(a.min()), median=float(np.median(a)),
                p95=float(np.quantile(a, .95)), max=float(a.max())) if len(a) else dict(n=0)


def audit(folder):
    raw = folder/'raw'
    remote = {s.split(maxsplit=1)[1].split(folder.name+'/', 1)[1]: s.split()[0]
              for s in (folder/'SHA256SUMS').read_text().splitlines()}
    manifest = read(raw/'manifest.json.zst')
    receipts = {}
    for relative, entry in manifest.items():
        p = raw/relative
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        assert h == entry['sha256'] == remote['raw/'+relative], p
        if entry.get('decoded_sha256'):
            assert hashlib.sha256(decoded(p)).hexdigest() == entry['decoded_sha256'], p
        receipts[str(p)] = h
    if (raw/'manifest-compression.json').exists():
        compression = read(raw/'manifest-compression.json')
        p = raw/compression['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest() == compression['sha256'] == remote['raw/'+p.name]
        assert hashlib.sha256(decoded(p)).hexdigest() == compression['decoded_sha256']
        receipts[str(p)] = compression['sha256']
    return receipts


def panorama(static, xy, arm, step=5):
    """Union across body yaw, pan=0; actual FK, pinhole AND raw fisheye bounds.

    Distinct physical wall faces/zone edges/doors, not repeated sample counts.
    A group needs two simultaneously visible samples spanning >=12 cm.
    """
    camera = Camera(); (origin, R), _ = camera.pose(look_servo(0, arm))
    lms = map_landmarks(static)
    # Explicit wall-base corners, separate from wall-face line observations.
    # Coincident rectangle corners are counted once; no synthetic corner cones.
    corners = sorted({(x,y) for _,a,b,c,d in wall_rects(static) for x in (a,b) for y in (c,d)
                      if static['bounds_m'][0]<x<static['bounds_m'][1] and static['bounds_m'][2]<y<static['bounds_m'][3]})
    lms += [dict(xy=p,group=f'corner:{p}',type='wall_corner',range=2.5,two_sided=True) for p in corners]
    points = np.array([l['xy'] for l in lms])
    normals = np.array([l.get('normal', [0, 0]) for l in lms])
    ranges = np.array([2.5 if l['type'] == 'wall' else l['range'] for l in lms])
    two = np.array([l.get('two_sided', False) for l in lms])
    rects = wall_rects(static); found = {}; best = 0
    for yaw in np.deg2rad(np.arange(0, 360, step)):
        rot = rotation(yaw); cw = xy+rot@origin[:2]
        local = (points-xy)@rot
        q = (np.c_[local, np.zeros(len(local))]-origin)@R
        uv = (q@camera.K.T)[:, :2]/np.maximum(q[:, 2:], 1e-8)
        rawuv = cv2.fisheye.projectPoints(q.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                    camera.K, np.array(CAMERA_FISHEYE_D))[0].reshape(-1, 2)
        ok = (q[:, 2] > .05) & (np.linalg.norm(points-cw, axis=1) <= ranges)
        ok &= two | (((cw-points)*normals).sum(1) > 0)
        for screen in (uv, rawuv):
            ok &= (screen[:, 0] >= 12) & (screen[:, 0] <= 628) & (screen[:, 1] >= 12) & (screen[:, 1] <= 468)
        groups = collections.defaultdict(list)
        for i in np.flatnonzero(ok):
            d = points[i]-cw; end = points[i]-.03*d/np.linalg.norm(d)
            if not any(_segment_hits_rect(cw, end, r) for r in rects):
                groups[lms[i]['group']].append(i)
        seen = {}
        for group, ids in groups.items():
            p = points[ids]
            if lms[ids[0]]['type']=='wall_corner' or (len(ids) >= 2 and np.max(np.linalg.norm(p[:, None]-p[None], axis=2)) >= .12):
                seen[group] = lms[ids[0]]['type']
        found.update(seen); best = max(best, len(seen))
    normal_rank = np.linalg.matrix_rank([l['normal'] for l in lms if l['group'] in found and 'normal' in l]) if found else 0
    return dict(groups=found, counts=dict(collections.Counter(found.values())),
                n=sum(k!='wall_corner' for k in found.values()),
                point_landmarks=sum(k in ('wall_corner','door') for k in found.values()),
                normal_rank=int(normal_rank), best_single_view=best)


def integrated(teacher, yaw_sign=1):
    """Reproduce the runner's issued-wheel integration at each logged tick."""
    pose = np.zeros(3); out = []
    for row in teacher:
        out.append(pose.copy())
        dt = np.clip(np.array(row['wheel_until'])-row['t'], 0, .1)
        wheels = np.asarray(row['wheels'])
        # Lateral shifts integrate each wheel's own PWM lease in the runner.
        if row['teacher_phase'] == 'shift' and len(set(np.round(dt[wheels != 0], 9))) > 1:
            motion = odometry(wheels*dt/.1, .1)
        else:
            motion = odometry(wheels, max(dt[wheels != 0], default=0.))
        pose[:2] += rotation(pose[2])@motion[:2]
        pose[2] += yaw_sign*motion[2]
    return np.array(out)


def main():
    hashes = {}; runs = []; grids = []; clegs = []; bsites = []; yaw_views = []; reviewed = []
    maps = {}
    for no in range(8):
        folder = RAW/f'release7-diagnostic-{no:02d}-a2314b16'; raw = folder/'raw'
        hashes.update(audit(folder))
        result = read(raw/'result.json.zst'); plan = read(raw/'plan.json'); scene = read(raw/'scene.json')
        static = resolve(plan['map_id'])[0]; assert digest(static) == scene['static_map_sha256']
        assert scene['weld'] == 'off'; maps[plan['map_id']] = static
        evaluation = rows(raw/'eval-only.jsonl.zst')
        # Evaluation has a final settle section and can repeat the last release clock.
        evaluation = sorted({round(e['t'], 5): e for e in evaluation}.values(), key=lambda e:e['t'])
        et = np.array([e['t'] for e in evaluation])
        teachers = {r: rows(raw/f'teacher-{r}.jsonl.zst') for r in ('r1', 'r2')}
        run = dict(run=folder.name, seed=plan['seed'], map_id=plan['map_id'], success=result['release_success'],
            outcome=result['release_outcome'], audit={k:result['input_audit'][k] for k in ('held_world_reads','invisible_measurements')},
            active=result['active_observation'], robots={})
        for rid in ('r1', 'r2'):
            t = teachers[rid]; times = np.array([x['t'] for x in t]); local = result['lookaround_result'][rid]
            v = local['localizer']['views']; ev = local['evaluation']['views']; sweeps = local['evaluation']['sweeps']
            run['robots'][rid] = dict(frames=len(v), nonempty=sum(bool(x['wall_points']+x['floor_lines']+x['doors']) for x in v),
                detections={k:sum(x[k] for x in v) for k in ('wall_points','floor_lines','doors')},
                sweep_errors=[dict(t=s['t0']+s['sim_s'], accepted=s['decision']['accepted'],
                    xy_m=s['after']['error_xy_m'], yaw_deg=s['after']['error_yaw_deg']) for s in sweeps])
            for view, truth in zip(v, ev):
                assert abs(view['t']-truth['t']) < 1e-5
                command_delta=view['command_pose'][2]-v[0]['command_pose'][2]
                actual_delta=truth['truth'][2]-ev[0]['truth'][2]
                yaw_views.append(dict(seed=plan['seed'], robot=rid, t=view['t'],
                    commanded_deg=math.degrees(wrap(command_delta)), actual_deg=math.degrees(wrap(actual_delta)),
                    error_deg=math.degrees(wrap(command_delta-actual_delta)),
                    sign_corrected_error_deg=math.degrees(wrap(-command_delta-actual_delta))))
            # Every setdown: released_here appears as holding true -> false.
            release_indices=[i for i in range(1,len(t)) if t[i-1]['holding_belief'] and not t[i]['holding_belief']]
            commands=integrated(t)
            for i in release_indices:
                release=t[i]['t']; start=0
                prior=[s for s in sweeps if s['t0']+s['sim_s'] < release and s['decision']['accepted']]
                if prior:start=int(np.argmin(abs(times-(prior[-1]['t0']+prior[-1]['sim_s']))))
                # Ground truth is used ONLY to score a counterfactual perfect anchor.
                a=int(np.argmin(abs(et-times[start]))); b=int(np.argmin(abs(et-release)))
                # The first available truth clock is t0+0.1: align both clocks.
                start=int(np.argmin(abs(times-et[a])))
                p0=np.array(evaluation[a]['robots'][rid]['pose']); p1=np.array(evaluation[b]['robots'][rid]['pose'])
                pred_xy=p0[:2]+rotation(p0[2]-commands[start,2])@(commands[i,:2]-commands[start,:2])
                pred_yaw=p0[2]+commands[i,2]-commands[start,2]
                error=float(np.linalg.norm(pred_xy-p1[:2])); angle=float(wrap(pred_yaw-p1[2]))
                clegs.append(dict(seed=plan['seed'],robot=rid,release_t=release,anchor_t=float(times[start]),
                    anchor_kind='last_accepted_setdown_sweep' if prior else 'release_handoff_perfect_counterfactual',
                    preceding_map_error_m=prior[-1]['after']['error_xy_m'] if prior else None,
                    preceding_map_error_yaw_deg=prior[-1]['after']['error_yaw_deg'] if prior else None,
                    command_distance_m=float(np.linalg.norm(np.diff(commands[start:i+1,:2],axis=0),axis=1).sum()),
                    drift_xy_m=error,drift_yaw_deg=math.degrees(angle),ratio_to_4cm=error/.04,
                    point_0_30m_error_upper_m=error+2*.30*abs(math.sin(angle/2))))
                # First sweep after this release is the original .15 m backoff site.
                following=[s for s in sweeps if s['t0']>release]
                if not following:continue
                when=following[0]['t0']; e=evaluation[int(np.argmin(abs(et-when)))]; p=np.array(e['robots'][rid]['pose'])
                beam=np.array(e['beam']['pose']); axis=np.array([math.cos(beam[2]),math.sin(beam[2])])
                ends=np.array([beam[:2]-.30*axis,beam[:2]+.30*axis]); vv=ends[1]-ends[0]
                def clearance(forward):
                    center=p[:2]+forward*np.array([math.cos(p[2]),math.sin(p[2])])
                    closest=ends[0]+np.clip((center-ends[0])@vv/(vv@vv),0,1)*vv
                    return float(np.linalg.norm(center-closest))
                beam_turn=min(clearance(f) for f in np.linspace(0,.10,11))
                beam_back=min(clearance(f) for f in np.linspace(-.10,0,11))
                wall_back=min(rect_distance(p[:2]+f*np.array([math.cos(p[2]),math.sin(p[2])]),r)
                    for f in np.linspace(-.10,0,11) for r in keepout_rects(static,perimeter=True))
                bsites.append(dict(seed=plan['seed'],robot=rid,t=when,release_t=release,pose=p.tolist(),
                    beam_centerline_at_site_m=clearance(0),beam_min_on_retrace_m=beam_turn,
                    beam_blocks_retrace_turn=beam_turn<.22,beam_blocks_in_place_turn=clearance(0)<.22,
                    beam_min_on_backstep_m=beam_back,beam_blocks_backstep=beam_back<.22,
                    wall_min_on_backstep_m=wall_back,wall_blocks_backstep=wall_back<.33))
        if no in (3,7):
            files=sorted((raw/'eval-overview').glob('*-release-*.jpg'))
            for i in sorted(set([0,len(files)-1,*[round((len(files)-1)*j/7) for j in range(1,7)]])):
                for sub in ('eval-overview','eval-own/r1','eval-own/r2'):
                    p=raw/sub/files[i].name
                    reviewed.append(dict(path=str(p),sha256=hashes[str(p)],t=teachers['r1'][int(p.name[:6])]['t']))
        runs.append(run)
    for map_id,static in maps.items():
        cx,cy=static['regions']['zone_A']['center_m'];hx,hy=static['regions']['zone_A']['half_extents_m']
        for arm_name,arm in (('surroundings',LOOK_ARM_V2),('floor',LOOK_ARM)):
            samples=[]
            for x in np.arange(cx-hx+.025,cx+hx,.05):
                for y in np.arange(cy-hy+.025,cy+hy,.05):
                    samples.append(dict(x=float(x),y=float(y),**panorama(static,np.array([x,y]),arm)))
            counts=[s['n'] for s in samples]
            grids.append(dict(map_id=map_id,map_sha256=digest(static),region='zone_A',arm=arm_name,
                n=len(samples),zero=sum(n==0 for n in counts),distribution=dict(collections.Counter(counts)),
                counts=stats(counts),by_type={kind:stats([s['counts'].get(kind,0) for s in samples]) for kind in ('wall','zone_edge','door','wall_corner')},
                point_landmark_distribution=dict(collections.Counter(s['point_landmarks'] for s in samples)),
                zero_point_landmarks=sum(s['point_landmarks']==0 for s in samples),
                rank_below_2=sum(s['normal_rank']<2 for s in samples),samples=samples))
            print(map_id,arm_name,'n=',len(samples),'zero=',sum(n==0 for n in counts),flush=True)
    moving=[v for v in yaw_views if abs(v['commanded_deg'])>20]
    summary=dict(source_sha='a2314b16d6d3c52d843fbde59fe7bda4eb8273bf',verified_files=len(hashes),verified_runs=8,
        runs=runs,reviewed_frames=reviewed,grid=[{k:v for k,v in g.items() if k!='samples'} for g in grids],
        b=dict(robot_setdown_sites=len(bsites),beam_blocks_retrace_turn=sum(s['beam_blocks_retrace_turn'] for s in bsites),
               beam_blocks_in_place_turn=sum(s['beam_blocks_in_place_turn'] for s in bsites),
               beam_blocks_backstep=sum(s['beam_blocks_backstep'] for s in bsites),wall_blocks_backstep=sum(s['wall_blocks_backstep'] for s in bsites),
               observed_guard_rejections=[dict(seed=r['seed'],**e) for r in runs for e in r['active'] if e.get('reason')=='released_beam_turn_clearance']),
        c=dict(incoming_relocalization_anchors=0,first_setdown_robot_legs=stats([x['drift_xy_m'] for x in clegs if x['anchor_kind'].startswith('release_handoff')]),
               later_setdown_robot_legs=stats([x['drift_xy_m'] for x in clegs if not x['anchor_kind'].startswith('release_handoff')]),
               later_over_4cm=sum(x['drift_xy_m']>.04 for x in clegs if not x['anchor_kind'].startswith('release_handoff')),
               note='No incoming route in these starts. Perfect evaluation anchors isolate command drift; not deployable truth initialization.'),
        yaw=dict(rotated_capture_count=len(moving),legacy_abs_error_deg=stats([abs(x['error_deg']) for x in moving]),
                 sign_only_abs_error_deg=stats([abs(x['sign_corrected_error_deg']) for x in moving])),
        scope='Saved JPEG review, static FK/map visibility and command replay. No physics/render or remote execution. Static union is an optimistic visibility ceiling, not observable unique pose.')
    detail=dict(hashes=hashes,grid=grids,run_details=runs,clearance_sites=bsites,drift_legs=clegs,yaw_views=yaw_views)
    target=BASE/'release8-analysis-detail.json.zst'
    target.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=json.dumps(detail).encode()))
    summary['detail']=dict(path=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    (BASE/'release8-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('verified_files','b','c','yaw')},indent=2))


if __name__=='__main__':main()
