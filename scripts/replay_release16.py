"""Census of locally retrieved beam-release own RGB, not a simulator replay.

Native input and 320x240 review JPEGs are separate strata. Copies are deduped
by (run, relative path, sha256), NOT by identical pixels at different times.
Truth is read only by score_direction(), after perception/decision extraction.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

import cv2
import numpy as np
from harness.vision_loc_protocol import load_vis3
from scripts.replay_release14 import decoded
from sim import release14, release15, release16
from sim.global_landmark_localization import GlobalLandmarkMatcher
from sim.lookaround_localization import Camera, OwnPose
from sim.visible_belief import odometry

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('eval-own', 'eval-regrasp-input', 'eval-lookaround-input')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(raw, name, *, lines=False, hashes=None):
    p = raw/name
    if not p.exists(): p = raw/(name+'.zst')
    if not p.exists(): return [] if lines else {}
    b = decoded(p)
    if hashes is not None: hashes[str(p)] = dict(sha256=sha(p), decoded_sha256=hashlib.sha256(b).hexdigest())
    return [json.loads(l) for l in b.splitlines()] if lines else json.loads(b)


def relative_image(path):
    for kind in KINDS:
        if kind in path.parts:
            return '/'.join(path.parts[path.parts.index(kind):])
    m = re.match(r'(eval-own)_(r[12])_(.+)', path.name)
    return '/'.join(m.groups()) if m else None


def census(raw_root, reports):
    runs = {}; fingerprints = defaultdict(list); payload_hashes = {}
    for raw in sorted(raw_root.glob('*/raw')):
        name = raw.parent.name
        if not (name.startswith(('release', 'r12d-', 'r14d-', 'r15d-', 'probe-setdown-'))): continue
        result = read(raw, 'result.json', hashes=payload_hashes)
        plan = read(raw, 'plan.json', hashes=payload_hashes)
        manifest = read(raw, 'manifest.json', hashes=payload_hashes)
        runs[name] = dict(raw=raw, result=result, plan=plan, manifest=manifest)
        for rel, value in manifest.items():
            if relative_image(Path(rel)):
                fingerprints[(relative_image(Path(rel)), value['sha256'])].append(name)
    frames = {}; excluded = Counter(); unresolved = []
    for root in (raw_root, reports):
        for p in sorted(root.rglob('*')):
            if p.suffix.lower() not in ('.jpg', '.jpeg', '.png'): continue
            rel = relative_image(p)
            if rel is None:
                excluded['not_original_own_frame'] += 1; continue
            digest = sha(p); matches = fingerprints.get((rel, digest), [])
            named = [name for name in runs if name in p.parts]
            # Older report folders flatten/shorten the original run names.
            # Still require the chosen run's exact relative-path JPEG hash.
            for folder, alias in {'release-gate-39-frames':'release-gate-39-4a69e6bc',
                                  'rg63201b88-74940':'release6-diagnostic-07-63201b88'}.items():
                if folder in p.parts:
                    if alias not in matches: raise ValueError('report alias hash mismatch: '+str(p))
                    named = [alias]
            release_path = any(re.search(r'release|r1[245]d|r7diag|rg63201b88', part) for part in p.parts[:-1])
            if named:
                name = named[0]
                if matches and name not in matches: raise ValueError('manifest identity mismatch: '+str(p))
            elif len(matches) == 1: name = matches[0]
            elif release_path:
                unresolved.append(dict(path=str(p), relative=rel, sha256=digest, matching_runs=matches)); continue
            else:
                excluded['other_task_own_frame'] += 1; continue
            expected = runs[name]['manifest'].get(rel, {}).get('sha256')
            if expected and expected != digest: raise ValueError('image hash mismatch: '+str(p))
            key = (name, rel, digest)
            if key in frames:
                frames[key]['copies'].append(str(p)); continue
            frames[key] = dict(run=name, relative=rel, path=str(p), sha256=digest,
                               manifest_verified=expected == digest, copies=[])
    return runs, list(frames.values()), dict(excluded), unresolved, payload_hashes


def context(run, hashes):
    raw, result = run['raw'], run['result']
    rows = {r: read(raw, f'teacher-{r}.jsonl', lines=True, hashes=hashes) for r in ('r1','r2')}
    refs = {r['path']: r for r in result.get('regrasp_input_frames', [])}
    for rid, record in result.get('lookaround_result', {}).items():
        for v in record.get('localizer', {}).get('views', []):
            if 'input_jpeg' in v: refs[v['input_jpeg']] = dict(v, robot=rid)
    return dict(rows=rows, refs=refs)


def stamp(frame, run, ctx):
    rel = frame['relative']; rid = rel.split('/')[1]; name = Path(rel).name
    ref = ctx['refs'].get(rel)
    if ref is not None: return ref['t'], ref.get('label', 'lookaround')
    m = re.match(r'(\d+)-(prefix|release-.+)\.jpg', name)
    ts = ctx['rows'].get(rid, [])
    if m and ts:
        t0 = ts[0]['t']
        if m[2] == 'prefix':
            held = run['result'].get('prefix', {}).get('held_sim_s')
            if held is None: return None, m[2]
            t0 -= held
        return t0+int(m[1])*.1, m[2]
    return None, Path(rel).stem


def nearest(rows, at, tolerance=1e-5):
    if at is None or not rows: return None
    row = min(rows, key=lambda r: abs(r['t']-at))
    return row if abs(row['t']-at) < tolerance else None


def issued_row(rows, at):
    # On the terminal failure tick the capture precedes the early loop break,
    # so there is no teacher row at that timestamp. Use the last issued row
    # within one tick, explicitly report its age; never borrow a future row.
    if at is None: return None
    candidates = [r for r in rows if -1e-6 <= at-r['t'] <= .101]
    return max(candidates, key=lambda r:r['t']) if candidates else None


def restore_map(run, ctx, rid, at):
    rec = run['result'].get('lookaround_result', {}).get(rid, {}).get('localizer', {})
    dec = rec.get('decision') or {}
    views = rec.get('views', [])
    if not dec.get('accepted') or 'proposed' not in dec or not views: return None
    last_view = max(v['t'] for v in views)
    if last_view > at+1e-6: return None  # Never use a future RGB fix.
    own = OwnPose(dec['proposed'], dec['sigma'][0], dec['sigma'][2])
    own.P = np.diag(np.asarray(dec['sigma'])**2)
    for row in ctx['rows'][rid]:
        if row['t'] < last_view-1e-6 or row['t'] >= at-1e-6: continue
        dt = min(.1, at-row['t'])
        effort = [w*max(0.,min(dt,u-row['t']))/.1 for w,u in zip(row['wheels'],row['wheel_until'])]
        own.propagate(*odometry(effort,.1,'native_yaw_v1'))
    static = json.loads((ROOT/'maps/zones'/f"{run['plan']['map_id']}.json").read_text())
    return SimpleNamespace(own=own,map_pose_known=True,decision=dec,global_matcher=GlobalLandmarkMatcher(static))


def score_direction(feature, truth, row, rid, camera):
    """Evaluation-only GT endpoints/body pose + commanded FK projection proxy.

    Actual camera extrinsics / measured joints are absent: this is explicitly
    NOT exact pixel ground truth. Do not return this record to the controller.
    """
    if feature.get('line') is None or truth is None or row is None: return None
    cam, _ = camera.pose({int(k):v for k,v in row['pwm'].items()})
    if cam is None: return None
    origin, rot = cam; pose = truth['robots'][rid]['pose']
    points = np.asarray(list(truth['beam']['ends'].values()), float)
    c,s = math.cos(pose[2]),math.sin(pose[2])
    points[:,:2] = (points[:,:2]-pose[:2])@np.array([[c,-s],[s,c]])
    optical = (points-origin)@rot
    # Homogeneous line remains defined when the far endpoint is behind camera.
    line = np.cross(*(optical@camera.K.T))
    if np.linalg.norm(line[:2]) < 1e-8: return None
    direction = np.array([-line[1],line[0]])
    slope = feature['slope_error']*640/192
    predicted = np.array([slope,1.])
    cosine = abs(float(direction@predicted))/(np.linalg.norm(direction)*np.linalg.norm(predicted))
    return math.degrees(math.acos(float(np.clip(cosine,0.,1.))))


def category(feature):
    if feature['valid']: return 'valid'
    return 'ambiguous' if any(s in feature['reason'] for s in ('ambiguous','nonlinear')) else 'unobserved'


def feature_angle(feature):
    return math.degrees(math.atan(feature['slope_error']*640/192)) if feature.get('line') is not None else None


def summarize(rows):
    out = {}
    for model in ('release14','release15','release16'):
        counts = Counter(category(row[model]) for row in rows)
        pairs = angle_jumps = position_jumps = 0
        for seq in group(rows, lambda r:(r['run'],r['robot'],r['stream'])).values():
            seq = sorted((r for r in seq if r['t'] is not None),key=lambda r:r['t'])
            for a,b in zip(seq,seq[1:]):
                # No bridging missing/ambiguous direction or long sampling gaps.
                dt = b['t']-a['t']; fa,fb = a[model],b[model]
                if not 1e-6 < dt <= 1.01 or fa.get('line') is None or fb.get('line') is None: continue
                pairs += 1
                delta = abs(feature_angle(fa)-feature_angle(fb)); delta = min(delta,180-delta)
                angle_jumps += delta > 10
                position_jumps += abs(fa['center_error']-fb['center_error'])*640 > 64
        errors = [r['evaluation_direction_error_deg'][model] for r in rows if r['evaluation_direction_error_deg'].get(model) is not None]
        out[model] = dict(N=len(rows),counts={k:counts[k] for k in ('valid','ambiguous','unobserved')},
            rates={k:counts[k]/len(rows) for k in ('valid','ambiguous','unobserved')},
            direction_available=sum(r[model].get('line') is not None for r in rows),continuity_pairs=pairs,
            angle_jumps_gt10deg=angle_jumps,position_jumps_gt64px=position_jumps,
            direction_error_proxy_N=len(errors),direction_error_proxy_median_deg=float(np.median(errors)) if errors else None,
            direction_error_proxy_p90_deg=float(np.quantile(errors,.9)) if errors else None)
    out['band_split_frames'] = sum(r['band_split'] for r in rows)
    out['collinear_merge_frames'] = sum(r['release16'].get('merged_components',0)>0 for r in rows)
    return out


def group(rows, key):
    groups = defaultdict(list)
    for r in rows: groups[key(r)].append(r)
    return groups


def replay(raw_root, reports, out):
    runs,frames,excluded,unresolved,hashes = census(raw_root,reports)
    if unresolved:
        (out/'unresolved.json').write_text(json.dumps(unresolved,indent=2)+'\n')
        raise ValueError(f'{len(unresolved)} unidentified release frames; see unresolved.json')
    u = load_vis3()[0].mp.undistort; camera = Camera(); results = []
    for name, items in sorted(group(frames,lambda f:f['run']).items()):
        run = runs[name]; ctx = context(run,hashes)
        truth = [r for r in read(run['raw'],'eval-only.jsonl',lines=True,hashes=hashes) if 'robots' in r and 'beam' in r]
        for item in items:
            rid = item['relative'].split('/')[1]; frame = cv2.imread(item['path'])
            if frame is None: raise ValueError('cannot decode: '+item['path'])
            h,w = frame.shape[:2]
            if (w,h) not in ((320,240),(640,480)): raise ValueError('unexpected size: '+str((w,h)))
            stream = item['relative'].split('/')[0]; at,label = stamp(item,run,ctx)
            # Review pixels are resized only for calibration, never called native.
            frame = u(frame if (w,h)==(640,480) else cv2.resize(frame,(640,480),interpolation=cv2.INTER_LINEAR))
            end = run['plan'].get('roles',{}).get(rid, 'teal' if rid=='r1' else 'blue')
            old14 = release14.line_features(frame); old15 = release15.line_features(frame,end)
            new = release16.line_features(frame,end)
            row = issued_row(ctx['rows'][rid],at)
            record = dict(item,robot=rid,t=at,label=label,stream=stream,resolution=[w,h],
                          release14=old14,release15=old15,release16=new)
            record['command_age_s'] = None if row is None else max(0.,at-row['t'])
            # Split count requires two significant shaft components in ONE
            # selected union object, not simply new.valid and old.ambiguous.
            selected,_ = release16.object_mask(frame,end)
            shaft = release16.beam_mask(frame)&selected
            _,_,stats,_ = cv2.connectedComponentsWithStats(shaft.astype('uint8'))
            areas = sorted(stats[1:,cv2.CC_STAT_AREA].tolist(),reverse=True)
            record['band_split'] = bool(new['valid'] and len(areas)>1 and areas[1]>.3*areas[0])
            record['shaft_component_areas'] = areas[:3]
            if stream=='eval-regrasp-input' and label in ('line_recheck','realign_back','realign_final') and row:
                pwm = {int(k):v for k,v in row['pwm'].items()};loc = restore_map(run,ctx,rid,at)
                for model,f in [('release15',old15),('release16',new)]:
                    try:
                        record[model+'_proposal'] = release15.line_step(f,camera,pwm,clearance=lambda *a:True)
                        record[model+'_map_gated'] = None if loc is None else release15.line_step(f,camera,pwm,clearance=lambda *a:release15.map_motion_clear(loc,*a))
                    except (ValueError,np.linalg.LinAlgError) as error:
                        record[model+'_replay_error'] = str(error)
            # All decisions above are complete before any truth scoring.
            ev = nearest(truth,at)
            record['evaluation_direction_error_deg'] = {m:score_direction(record[m],ev,row,rid,camera) for m in ('release14','release15','release16')}
            record['evaluation_direction_status'] = {
                m: ('scored_command_FK_proxy' if record['evaluation_direction_error_deg'][m] is not None
                    else 'no_line' if record[m].get('line') is None
                    else 'no_exact_truth_tick' if ev is None
                    else 'no_recent_command' if row is None
                    else 'command_camera_unqualified_or_degenerate')
                for m in ('release14','release15','release16')}
            record['evaluation_pose_available'] = ev is not None
            results.append(record)
        print(name,len(items),Counter(r['release16']['reason'] for r in results if r['run']==name),flush=True)
    (out/'frames.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in results))
    summary = dict(schema='ugrp.release16.offline.v1',profile=release16.PROFILE,
        scope='all locally retrieved beam-release own JPEG files in the two roots; copies deduplicated; old-state decisions only',
        raw_roots=[str(raw_root),str(reports)],frame_count=len(results),copies=sum(len(f['copies']) for f in frames),
        unresolved=unresolved,excluded=excluded,all=summarize(results),
        by_run={n:summarize(rs) for n,rs in sorted(group(results,lambda r:r['run']).items())},
        by_stream={n:summarize(rs) for n,rs in sorted(group(results,lambda r:r['stream']+f"/{r['resolution'][0]}x{r['resolution'][1]}").items())},
        line_rechecks=summarize([r for r in results if r['label']=='line_recheck']),
        truth_direction_scope='GT beam endpoints/body XY+yaw with commanded camera FK; approximate evaluation proxy, actual camera extrinsics and measured joints unavailable',
        continuity_definition='consecutive same run/robot/stream, both directions available, 0<dt<=1.01 s; >10deg or >64px at row239.5; no interpolation',
        manifest_verified=sum(f['manifest_verified'] for f in frames),payload_hashes=hashes,
        physical_effect='unverified',simulation_calls=0,remote_host_connections=0,gate40_approved=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('frame_count','copies','all','by_stream','line_rechecks')},indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--reports',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);replay(a.raw_root,a.reports,a.out)
if __name__=='__main__': main()
