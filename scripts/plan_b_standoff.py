"""Offline B stand-off planning + projection check (static map + fixed camera only; no sim, no frames)."""
import argparse, json, math, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from harness import e2e_b_standoff as S


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True); a = ap.parse_args()
    b = S.load_board(); top, n, total = S.plan_standoffs(b, top=200)
    arr = np.array([[v['pose'][0], v['pose'][1], v['stand_off_m'], v['margin_px'], v['min_mark_px']] for v in top])
    ex = []
    for v in top[:5]:
        c = S.view_check(v['pose'], b)
        ex.append(dict(pose_xy_yaw_deg=[round(v['pose'][0], 2), round(v['pose'][1], 2), round(math.degrees(v['pose'][2]), 1)],
                       stand_off_m=round(v['stand_off_m'], 2), path_m_from_pickup_centre=round(v['path_m'], 2),
                       corner_pixels_uv=c['corners_px'], min_margin_to_unusable_px=round(c['margin_px'], 1), min_slot_mark_px=round(c['min_mark_px'], 1),
                       self_mask_overlap_px=c['self_mask_overlap_px']))
    # the e2e11 viewpoint class (0.8 m in front of the near edge, facing it) for contrast
    old = S.view_check([b['center'][0]-b['half'][0]-.7, b['center'][1], 0.], b)
    summary = dict(option=S.OPTION, board_map=str(S.MAP.relative_to(ROOT)), board_center_m=b['center'].tolist(), board_size_m=(2*b['half']).tolist(),
                   camera=dict(servo='SEARCH', note='height/pitch from servo FK (0.231 m, -18.1 deg), measured fisheye K/D, lens circle, own-body mask'),
                   cfg=S.CFG, search=n, admitted_before_pose_jitter=total, admitted_after_pose_jitter=len(top),
                   stand_off_m=dict(min=float(arr[:, 2].min()), median=float(np.median(arr[:, 2])), max=float(arr[:, 2].max())),
                   positions_x_m=[float(arr[:, 0].min()), float(arr[:, 0].max())], positions_y_m=[float(arr[:, 1].min()), float(arr[:, 1].max())],
                   best_five=ex, e2e11_style_close_view=dict(pose=[b['center'][0]-b['half'][0]-.7, float(b['center'][1]), 0.],
                                                              reason=old['reason'], margin_px=old['margin_px']))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'standoff-plan.json').write_text(json.dumps(summary, indent=1, default=float)); print(json.dumps(summary, indent=1, default=float))


if __name__ == '__main__': main()
