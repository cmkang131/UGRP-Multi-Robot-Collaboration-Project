"""Recount saved selfmap traces; evaluator-only pose pairing, no simulation."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np


def load(path):
    if not path.exists():
        path=Path(str(path)+'.zst')
    if not path.exists():return None
    raw=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()
    return raw


def obj(path):
    raw=load(path)
    return json.loads(raw) if raw else {}


def rows(path):
    raw=load(path)
    return [json.loads(v) for v in raw.splitlines()] if raw else []


def stats(values):
    return dict(N=len(values),min=float(min(values)),median=float(np.median(values)),p90=float(np.percentile(values,90)),max=float(max(values))) if values else dict(N=0)


def analyze(folder):
    raw=folder/'raw';trace=rows(raw/'trace.jsonl');truth=rows(raw/'eval_only/trajectory.jsonl')
    gt={round(r['t'],6):r for r in truth};errors=[];resolved_errors=[];registered_errors=[];rejections=Counter();visual=Counter()
    within=0
    for r in trace:
        reg=r.get('static_registration',{});diag=reg.get('reloc10_diagnostics',{})
        rejections.update(diag.get('rejection_reasons',[]));visual[r.get('visual_reason')]+=1
        t=gt.get(round(r['t'],6));p=reg.get('world_pose')
        if t is None or p is None:continue
        xy=math.dist(p[:2],t['robot_xyz_m'][:2]);yaw=abs((p[2]-t['robot_yaw_rad']+math.pi)%(2*math.pi)-math.pi)
        e=dict(t=r['t'],xy_m=xy,yaw_deg=math.degrees(yaw),within_10cm_5deg=xy<=.1 and yaw<=math.radians(5))
        errors.append(e)
        if 'pf_unresolved' not in diag.get('rejection_reasons',['pf_unresolved']):resolved_errors.append(e)
        if reg.get('registered'):registered_errors.append(e)
    def error_stats(es):return dict(N=len(es),xy_m=stats([e['xy_m'] for e in es]),yaw_deg=stats([e['yaw_deg'] for e in es]),within_10cm_5deg=sum(e['within_10cm_5deg'] for e in es))
    result=obj(raw/'result.json');first=obj(raw/'first30.json')
    out=dict(run=folder.name,source_sha=result.get('source_sha'),result=result,first30=first,frame_N=len(trace),
        features=stats([r.get('features',0) for r in trace]),matches=stats([r.get('matches',0) for r in trace]),inliers=stats([r.get('inliers',0) for r in trace]),
        static_features=stats([r.get('static_registration',{}).get('feature_count',0) for r in trace]),
        pf_resolved_N=len(resolved_errors),registered_N=sum(bool(r.get('static_registration',{}).get('registered')) for r in trace),
        reliable_N=sum(bool(r.get('static_registration',{}).get('resolved')) for r in trace),
        sensor_updates=sum(bool(r.get('static_registration',{}).get('updated')) for r in trace),
        rejection_reasons=dict(rejections),visual_reason=dict(visual),pf_error=error_stats(errors),pf_resolved_error=error_stats(resolved_errors),registered_error=error_stats(registered_errors),
        timing=obj(raw/'timing.json'),retrieval='text + selected own RGB; all RGB retained on GCP persistent disk',
        text_sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file() and p.suffix not in ('.jpg','.png')})
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=[analyze(f) for f in a.folders]
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for r in result:print(json.dumps({k:r[k] for k in ('run','frame_N','features','matches','inliers','static_features','pf_resolved_N','registered_N','pf_resolved_error')}))


if __name__=='__main__':main()
