"""Wall/floor IoU of a segmentation checkpoint on the dev static sets (torch env).  usage: eval_dev.py <ckpt> <out.json> [--pre rgb] [--xf name]"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import seg_ft

DEV = Path('/Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929/dev')
ap = argparse.ArgumentParser()
ap.add_argument('ckpt'); ap.add_argument('out')
ap.add_argument('--pre', default='rgb'); ap.add_argument('--xf', default='none'); ap.add_argument('--max-frames', type=int)
a = ap.parse_args()
seg = seg_ft.Seg(Path(a.ckpt), a.pre, xf=seg_ft.XFS[a.xf])
sets = {p.name: p for p in sorted(DEV.iterdir()) if (p / 'manifest.json').exists()}
res = seg_ft.eval_sets(seg, sets, a.max_frames)
Path(a.out).write_text(json.dumps({'ckpt': a.ckpt, 'sha256': seg.sha256, 'pre': a.pre, 'xf': a.xf, 'results': res}, indent=1))
for k, v in res.items():
    print(f"{k:24s} wallIoU {v['iou_wall']:.3f} floorIoU {v['iou_floor']:.3f} mIoU {v['miou']:.3f} frame-wall p10 {v['wall_iou_frame_p10']:.3f} med {v['wall_iou_frame_median']:.3f}")
