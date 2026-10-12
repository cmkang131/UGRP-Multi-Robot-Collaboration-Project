"""Offline evaluator over fetch-lite ledgers. Never imported by controllers."""
import argparse
import bisect
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


def rows(path):
    data = path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])
    return [json.loads(s) for s in data.splitlines() if s]


def digest(path):
    path = path if path.exists() else Path(str(path)+'.zst')
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def diagnose(run):
    contacts = rows(run/'raw/eval_only/contacts.jsonl')
    ct = [x['t'] for x in contacts]
    output, details, selection = {}, [], []
    for rid in ('r1', 'r2'):
        paths = [run/f'raw/robots/{rid}/{name}.jsonl' for name in ('ownmap', 'frames', 'commands')]
        paths += [run/f'raw/eval_only/{rid}/trajectory.jsonl', run/'raw/eval_only/contacts.jsonl']
        own, frames, commands, truth = [rows(p) for p in paths[:4]]
        ts = [r['t'] for r in truth]
        origin = frames[0]['sim_time']
        base = truth[min(range(len(ts)), key=lambda i: abs(ts[i]-origin))]
        yaw = base['robot_yaw_rad']; c, s = math.cos(yaw), math.sin(yaw)
        matched = []
        for row, frame in zip(own, frames):
            assert row['frame_id'] == frame['frame_id'] and row['sha256'] == frame['sha256']
            t = frame['sim_time']; idx = min(bisect.bisect_left(ts, t), len(ts)-1)
            idx = min((idx, max(0, idx-1)), key=lambda i: abs(ts[i]-t))
            assert abs(ts[idx]-t) < 1e-6, 'EXACT_CAMERA_TRUTH_ALIGNMENT_REQUIRED'
            gt = truth[idx]; dx, dy = [gt['robot_xyz_m'][i]-base['robot_xyz_m'][i] for i in (0,1)]
            actual = [c*dx+s*dy, -s*dx+c*dy]
            pc = row['pose_continuity']
            matched.append(dict(t=row['t'], frame=frame, actual=actual, gt_index=idx,
                map_error_m=math.dist(actual, pc['map_pose'][:2]),
                odom_error_m=math.dist(actual, pc['control_pose'][:2]),
                odom=pc['control_pose'], map=pc['map_pose']))
        intervals = []
        for a, b in zip(matched, matched[1:]):
            issued = math.dist(a['odom'][:2], b['odom'][:2])
            actual = sum(math.dist(x['robot_xyz_m'][:2], y['robot_xyz_m'][:2])
                for x,y in zip(truth[a['gt_index']:b['gt_index']], truth[a['gt_index']+1:b['gt_index']+1]))
            # Evaluation definition, not a controller threshold or proof of contact causality.
            translation = issued >= .005
            stalled = translation and actual < .2*issued
            other = set()
            for cr in contacts[bisect.bisect_left(ct,a['frame']['sim_time']):bisect.bisect_right(ct,b['frame']['sim_time'])]:
                for hit in cr['contacts']:
                    gs = [hit['geom1'],hit['geom2']]
                    if sum(g.startswith(rid+'__') for g in gs) == 1:
                        other.update(g for g in gs if not g.startswith(rid+'__') and g != 'floor')
            error_delta = [(b['odom'][i]-a['odom'][i])-(b['actual'][i]-a['actual'][i]) for i in (0,1)]
            intervals.append(dict(run=run.name, robot=rid, t0=a['t'], t1=b['t'], dt=b['t']-a['t'],
                frame_before=a['frame']['path'], frame_after=b['frame']['path'],
                before_sha256=a['frame']['sha256'], after_sha256=b['frame']['sha256'],
                expected_m=issued, actual_path_m=actual, translating=translation, stalled=stalled,
                contacts=sorted(other), local_increment_error_m=math.hypot(*error_delta),
                map_error_change_m=b['map_error_m']-a['map_error_m'],
                odom_error_change_m=b['odom_error_m']-a['odom_error_m'],
                map_error_m=b['map_error_m'], odom_error_m=b['odom_error_m']))
        segments = []
        for i, row in enumerate(intervals):
            if row['stalled']:
                if not segments or segments[-1]['end_index'] != i-1:
                    segments.append(dict(start_index=i, end_index=i))
                segments[-1]['end_index'] = i
        for seg in segments:
            part=intervals[seg['start_index']:seg['end_index']+1]
            seg.update(t0=part[0]['t0'], t1=part[-1]['t1'], duration_s=sum(r['dt'] for r in part),
                expected_m=sum(r['expected_m'] for r in part), actual_path_m=sum(r['actual_path_m'] for r in part),
                map_error_change_m=sum(r['map_error_change_m'] for r in part),
                odom_error_change_m=sum(r['odom_error_change_m'] for r in part),
                contacts=sorted(set(g for r in part for g in r['contacts'])))
        stalled=[r for r in intervals if r['stalled']]; trans=[r for r in intervals if r['translating']]
        def total(key): return sum(r[key] for r in stalled)
        contact_counts=Counter(g for r in stalled for g in r['contacts'])
        output[rid]=dict(intervals=len(intervals),translation_intervals=len(trans),stalled_intervals=len(stalled),
            stall_fraction=len(stalled)/max(1,len(trans)),stall_duration_s=total('dt'),stall_segments=len(segments),
            issued_during_stall_m=total('expected_m'),actual_path_during_stall_m=total('actual_path_m'),
            stall_local_increment_error_m=total('local_increment_error_m'),
            stall_net_map_error_change_m=total('map_error_change_m'),stall_net_odom_error_change_m=total('odom_error_change_m'),
            stall_contacts=dict(contact_counts),stalled_without_contact=sum(not r['contacts'] for r in stalled),
            map_error_max_m=max(r['map_error_m'] for r in matched),map_error_median_m=statistics.median(r['map_error_m'] for r in matched),
            odom_error_max_m=max(r['odom_error_m'] for r in matched),odom_error_median_m=statistics.median(r['odom_error_m'] for r in matched),
            first_over_1m_sim_s=next((r['t'] for r in matched if r['map_error_m']>1),None),
            longest_segments=sorted(segments,key=lambda r:r['duration_s'],reverse=True)[:5],sources=[digest(p) for p in paths])
        # Three longest stall windows (up to 4s each), three moving windows.
        starts=[max(0,s['start_index']-4) for s in sorted(segments,key=lambda r:r['duration_s'],reverse=True)[:3]]
        moving=[i for i,r in enumerate(intervals) if r['translating'] and r['actual_path_m']>=.8*r['expected_m']]
        starts += [moving[j] for j in (0,len(moving)//2,len(moving)-1)] if moving else []
        selected=sorted(set(i for start in starts for i in range(start,min(start+20,len(intervals)))))
        selection += [intervals[i] for i in selected]
        details += intervals
    return output, details, selection


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    result={};detail=[];selection=[]
    for run in sorted(a.root.glob('e2e10-*-r2')):
        r,d,s=diagnose(run);result[run.name]=r;detail+=d;selection+=s
    for name,value in [('diagnosis.json',result),('selected-intervals.json',selection),('intervals.json',detail)]:
        raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
        path=a.output/name;path.write_bytes(raw)
        if len(raw)>65536:
            subprocess.run(['zstd','-q',str(path)],check=True)
            assert subprocess.check_output(['zstd','-dc',str(path)+'.zst'])==raw
            path.unlink()
    print(json.dumps({r:{k:{f:v[f] for f in ('stall_fraction','stall_duration_s','issued_during_stall_m','actual_path_during_stall_m','map_error_max_m','first_over_1m_sim_s')} for k,v in robots.items()} for r,robots in result.items()},indent=2))


if __name__=='__main__':main()
