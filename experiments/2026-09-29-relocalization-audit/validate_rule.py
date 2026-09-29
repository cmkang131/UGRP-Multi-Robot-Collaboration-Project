"""Pixel-level check of the colour/column-scan structure rule against the geometry prediction (GT pose + map)."""
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geom, rule  # noqa: E402


def run(inv_path, n_cases=14, per=4, seed=3, out=None):
    inv = [r for r in json.load(open(inv_path)) if r['render_profile'] is None]
    random.seed(seed)
    random.shuffle(inv)
    valid = geom.full_valid()
    byst = {}
    for r in inv:
        byst.setdefault(r['stage'], []).append(r)
    rows = []
    for st, lst in byst.items():
        for r in lst[:n_cases]:
            c = r['dir']
            rb = json.load(open(c + '/robots.json'))
            tr = [json.loads(l) for l in open(c + '/eval_only/trace.jsonl')]
            tt = np.array([t['t'] for t in tr])
            for rid in ('r1', 'r2'):
                fr = rb[rid].get('frames') or []
                for f in random.sample(fr, min(per, len(fr))):
                    i = int(np.abs(tt - f['t']).argmin())
                    g = tr[i]['robots'][rid]
                    lab, _ = geom.predict_labels(f['commanded_servo'], g, 2)
                    lab = cv2.resize(lab.astype(np.uint8), (640, 480), interpolation=cv2.INTER_NEAREST)
                    wall_pred = ((lab == 1) | (lab == 2)) & valid
                    tm = geom.tag_mask(f['commanded_servo'], g) & valid
                    im = cv2.imread(f"{c}/frames/{rid}/{f['frame']:05d}.jpg")
                    stt, tag, beam, m = rule.structure(im, valid)
                    both = stt | tag
                    rows.append(dict(stage=st, load=f['report']['load_state'], pred=float(wall_pred.sum() / valid.sum()),
                                     rule=float(both.sum() / valid.sum()), tp=int((wall_pred & both).sum()),
                                     npred=int(wall_pred.sum()), nrule=int(both.sum()),
                                     tag_tp=int((tm & tag).sum()), ntagpred=int(tm.sum())))
    summary = []
    for st in byst:
        for ls in ('unloaded', 'loaded'):
            x = [a for a in rows if a['stage'] == st and a['load'] == ls]
            if not x:
                continue
            tp = sum(a['tp'] for a in x)
            p = np.array([a['pred'] for a in x])
            q = np.array([a['rule'] for a in x])
            summary.append(dict(stage=st, load=ls, n=len(x), pred_mean=float(p.mean()), rule_mean=float(q.mean()),
                                recall=tp / max(sum(a['npred'] for a in x), 1), precision=tp / max(sum(a['nrule'] for a in x), 1),
                                corr=float(np.corrcoef(p, q)[0, 1]) if p.std() > 0 and q.std() > 0 else None,
                                tag_recall=sum(a['tag_tp'] for a in x) / max(sum(a['ntagpred'] for a in x), 1)))
    for s in summary:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
    if out:
        json.dump(dict(rows=rows, summary=summary), open(out, 'w'))
    return summary


if __name__ == '__main__':
    run(sys.argv[1])
