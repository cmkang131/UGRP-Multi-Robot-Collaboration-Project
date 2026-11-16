"""Qualitative montage on B1 floor_light_v1 frames: undistorted RGB | seg-v2 | fine-tuned C_mix_rgb | teacher label (torch env)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2, numpy as np
import seg_ft
import vision_loc as vl
C = Path('/Users/changmin/projects/ugrp/outputs/carry-relocalization-b1-20260929/cohort/render_floor_light_v1')
O = Path('/Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929')
names = sys.argv[2:] or ['cp1_r1_p20_1500', 'cp3_r2_p20_1500', 'cp7_r1_p20_2030', 'cp2_r1_search_1500']
segs = {'seg-v2': seg_ft.Seg(seg_ft.SEG_V2), 'C_mix_rgb': seg_ft.Seg(O / 'model/C_mix_rgb/seg_lraspp_mbv3.pt')}
pal = np.array([[60, 60, 60], [40, 200, 40], [200, 60, 60], [60, 60, 220], [0, 0, 0]], np.uint8)   # floor grey, wall green, self red, object blue, bg black


def tile(lab):
    return cv2.resize(pal[np.clip(lab, 0, 4)][:, :, ::-1], (320, 240), interpolation=cv2.INTER_NEAREST)


rows = []
for n in names:
    bgr = cv2.imread(str(C / 'frames' / f'{n}.jpg'))
    und = cv2.resize(vl.mp.undistort(bgr), (320, 240), interpolation=cv2.INTER_AREA)
    lab = cv2.imread(str(C / 'eval_only/labels' / f'{n}.png'), cv2.IMREAD_UNCHANGED)
    cols = [und, tile(segs['seg-v2'].probs(bgr).argmax(2)), tile(segs['C_mix_rgb'].probs(bgr).argmax(2)), tile(lab)]
    for c, t in zip(cols, ['frame ' + n, 'seg-v2', 'fine-tuned (C)', 'teacher label']):
        cv2.putText(c, t, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1)
    rows.append(np.hstack(cols))
cv2.imwrite(sys.argv[1], np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])
