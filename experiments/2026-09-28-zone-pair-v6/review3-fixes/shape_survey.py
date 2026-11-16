"""Offline survey of the v6 shape fit on saved own frames (no physics, no model).

Inputs: each run's own input records + JPEGs (read only). The ground-truth grip
from eval_only/trace.jsonl is used ONLY to score the estimate afterwards.
Usage: shape_survey.py OUT_DIR [--source-rev REV]  (REV: git blob of zone_pair_relative.py)
"""
import argparse, bisect, glob, hashlib, importlib.util, json, math, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness import owncam_pair_beam_v2 as ob2
from harness.owncam_pair_beam import GRIP_INSET_M
RAW = ['/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5h-f87921dc52f7a3f12d41b4bc6ab5c30227890e8e',
       '/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5b-3ea2edc08e5addafaf3cedc934c463ad8e1635c8',
       '/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5g-c38f94e6c551d8c0fa9993945ff4df087754672e']


def module(rev):
    if rev is None:
        from harness import zone_pair_relative as rel
        return rel
    code = subprocess.check_output(['git', 'show', f'{rev}:harness/zone_pair_relative.py'], cwd=ROOT)
    path = Path(tempfile.mkdtemp())/'rel_at_rev.py'; path.write_bytes(code)
    spec = importlib.util.spec_from_file_location('rel_at_rev', path)
    rel = importlib.util.module_from_spec(spec); sys.modules['rel_at_rev'] = rel; spec.loader.exec_module(rel)
    return rel


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--source-rev')
    args = ap.parse_args(); rel = module(args.source_rev)
    post = {n: ob2.pose_of(n) for n in ('search', 'p45', 'inspect')}
    rows = []
    for root in RAW:
        for run in sorted(glob.glob(root+'/dev*')):
            if run.endswith('managed'):
                continue
            trace = [json.loads(l) for l in open(run+'/eval_only/trace.jsonl')]
            ts = [r['t'] for r in trace]
            for rid in ('r1', 'r2'):
                for f in sorted(glob.glob(f'{run}/inputs/{rid}/*.json')):
                    o = json.load(open(f)); sp = o['actuator_state']['servo_pulses']
                    if int(sp['1']) != 2000:
                        continue
                    servo = {int(k): int(v) for k, v in sp.items()}
                    img = open(run+'/'+o['image_file'], 'rb').read()
                    if len(rel.shape_points(img, servo)[0]) < 60:
                        continue
                    view = next((n for n, p in post.items() if all(servo[k] == p[k] for k in (3, 4, 5))), 'other')
                    fit, why = rel.shape_fit(img, servo)
                    g = trace[min(bisect.bisect_left(ts, o['sim_time']), len(ts)-1)]
                    rx, ry, ryaw = g['robots'][rid]; c = np.array(g['beam_corners'])[:, :2]
                    def base(p):
                        d = p-np.array([rx, ry])
                        return np.array([math.cos(ryaw)*d[0]+math.sin(ryaw)*d[1], -math.sin(ryaw)*d[0]+math.cos(ryaw)*d[1]])
                    near, far = sorted((base(c[[0, 2]].mean(0)), base(c[[4, 6]].mean(0))), key=np.linalg.norm)
                    gt = near+GRIP_INSET_M*(far-near)/np.linalg.norm(far-near)
                    row = dict(root=Path(root).name, run=Path(run).name, rid=rid, frame=o['frame_id'],
                               sha256=o['sha256'], view=view, reasons=list(why), gt_grip=gt.round(4).tolist())
                    if fit is not None:
                        row.update(fit_grip=np.round(fit['grip_base_m'], 4).tolist(),
                                   bound=round(fit['std_xy_m']+fit['bias_bound_m'], 4),
                                   err=round(float(np.linalg.norm(np.array(fit['grip_base_m'])-gt)), 4))
                    rows.append(row)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows).encode(); (out/'frames.json').write_bytes(data)
    fits = [r for r in rows if 'err' in r]
    summary = {'source_rev': args.source_rev or 'working tree', 'frames': len(rows), 'fits': len(fits),
               'ready_fits_bound_le_5cm': sum(r['bound'] <= .05 for r in fits),
               'violations_err_gt_bound': sum(r['err'] > r['bound'] for r in fits),
               'max_err_m': max((r['err'] for r in fits), default=None),
               'max_err_over_bound': max((r['err']/r['bound'] for r in fits), default=None),
               'first_reason': dict(Counter(r['reasons'][0] for r in rows)),
               'separate_component_excluded_fits': sum('SEPARATE_COMPONENT_EXCLUDED' in r['reasons'] for r in fits),
               'gt_grip_x_range_of_fits': [min((r['gt_grip'][0] for r in fits), default=None),
                                           max((r['gt_grip'][0] for r in fits), default=None)],
               'frames_json_sha256': hashlib.sha256(data).hexdigest(), 'raw_roots': RAW,
               'scope': 'saved own frames with open gripper and >=60 beam-colour points; GT used only to score'}
    (out/'summary.json').write_text(json.dumps(summary, indent=1)+'\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
