"""Offline off-vs-on evaluation of camera_calib=measured_v1. Detection sees pixels + commanded servo only;
ground truth (placements, stored true centres) is read after every prediction and written only to the evaluation record.

  partial <e2e11 selected-frames root> <partial-eval-rows.json.zst> <out.json>   (42 partial-B frames, SEARCH)
  cones   <frames dir with placements/evaluation json> <out.json>                (cones_v1)
"""
import json, math, subprocess, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import camera_calib
from harness.active_camera import SEARCH


def stats(v):
    v = np.asarray(v, float)
    return dict(n=int(v.size), median=float(np.median(v)), p90=float(np.percentile(v, 90)), max=float(v.max())) if v.size else dict(n=0)


def partial(root, rows_path, out):
    from harness.e2e_b_partial import detect_partial
    rows = json.loads(subprocess.check_output(['zstd', '-dc', rows_path]))
    sel = [r for r in rows if r['cls'] == 'partial']
    total = len(sel)
    sel = [r for r in sel if (Path(root)/r['run']/'raw/robots'/r['robot']/'rgb'/f"{r['frame_id']-1:05d}.jpg").exists()]
    print('partial frames', total, 'image present locally', len(sel))
    res = {}
    for mode in ('off', 'measured_v1'):
        camera_calib.set_mode(mode)
        recs = []
        for r in sel:
            img = Path(root)/r['run']/'raw/robots'/r['robot']/'rgb'/f"{r['frame_id']-1:05d}.jpg"
            rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
            got = detect_partial(rgb, dict(SEARCH), [0., 0., 0.])
            rec = dict(run=r['run'], robot=r['robot'], frame_id=r['frame_id'], accepted=len(got))
            if got:  # ---- evaluation only ----
                est = np.array(got[0]['center_robot_m']); tc = np.array(r['true_center_robot_m'])
                rec.update(est=est.tolist(), err_vec=(est-tc).tolist(), err_m=float(np.linalg.norm(est-tc)),
                           stored_off_est=r['est_center_robot_m'])
            recs.append(rec)
        acc = [x for x in recs if x['accepted']]
        ev = np.array([x['err_vec'] for x in acc]) if acc else np.zeros((0, 2))
        res[mode] = dict(n_frames=len(sel), n_labeled_partial_total=total, accepted=len(acc), err_m=stats([x['err_m'] for x in acc]),
                         mean_err_vec_xy_cm=(ev.mean(0)*100).tolist() if len(ev) else None,
                         std_err_vec_xy_cm=(ev.std(0)*100).tolist() if len(ev) else None, status=camera_calib.status(), rows=recs)
    off = {(x['run'], x['robot'], x['frame_id']): x for x in res['off']['rows']}
    res['off_reproduces_stored_est_max_abs_m'] = float(max((np.abs(np.array(x['est'])-np.array(x['stored_off_est'])).max()
                                                            for x in off.values() if x['accepted']), default=float('nan')))
    Path(out).write_text(json.dumps(res, indent=1))
    for m in ('off', 'measured_v1'):
        print(m, 'accepted', res[m]['accepted'], '/', res[m]['n_frames'], 'err', {k: round(v, 4) for k, v in res[m]['err_m'].items()},
              'mean xy err cm', np.round(res[m]['mean_err_vec_xy_cm'], 2), 'std', np.round(res[m]['std_err_vec_xy_cm'], 2), res[m]['status'])
    print('off reproduces stored est, max abs diff m:', res['off_reproduces_stored_est_max_abs_m'])


def cones(src, out):
    from harness import e2e_b_cones as C
    from harness.e2e_rgb_gate import default_cone_layout
    src = Path(src)
    ev = json.loads((src/'evaluation_ground_truth.json').read_text())['placements']
    layout = default_cone_layout()
    bc = json.loads(Path('maps/zones_e2e/zone_wide_door_e2e_b80_cones_v1.json').read_text())['regions']['zone_B']['center_m']
    res = {}
    for mode in ('off', 'measured_v1'):
        camera_calib.set_mode(mode)
        recs = []
        for e in ev:
            rgb = cv2.cvtColor(cv2.imread(str(src/f"f{e['frame']:03d}.jpg")), cv2.COLOR_BGR2RGB)
            d = {}
            fit = C.detect_cones(rgb, dict(SEARCH), (0., 0., 0.), layout, diagnostics=d)
            rec = dict(frame=e['frame'], accepted=fit is not None, n_blobs=d.get('cone_blobs'), reason=d.get('cone_fit_reason'),
                       ranges=[round(c['range_m'], 3) for c in d.get('cones', [])])
            x, y, yaw = e['robot']; c, s = math.cos(yaw), math.sin(yaw)   # ---- evaluation only ----
            true = [c*(bc[0]-x)+s*(bc[1]-y), -s*(bc[0]-x)+c*(bc[1]-y)]
            if fit:
                rec['pos_err_m'] = float(np.hypot(fit['center_robot_m'][0]-true[0], fit['center_robot_m'][1]-true[1]))
                rec['yaw_err_deg'] = float(math.degrees(abs((fit['yaw_robot_rad']-(-yaw) +math.pi/2) % math.pi-math.pi/2)))
            recs.append(rec)
        acc = [r for r in recs if r['accepted']]
        res[mode] = dict(n_frames=len(recs), accepted=len(acc), frames_ge1_blob=sum(1 for r in recs if (r['n_blobs'] or 0) >= 1),
                         frames_ge3_blobs=sum(1 for r in recs if (r['n_blobs'] or 0) >= 3), pos_err_m=stats([r['pos_err_m'] for r in acc]),
                         status=camera_calib.status(), rows=recs)
    Path(out).write_text(json.dumps(res, indent=1))
    for m in ('off', 'measured_v1'):
        r = res[m]; print(m, 'accepted', r['accepted'], '/', r['n_frames'], 'blobs>=1', r['frames_ge1_blob'], '>=3', r['frames_ge3_blobs'],
                          'pos_err', {k: round(v, 4) for k, v in r['pos_err_m'].items()}, r['status'])


if __name__ == '__main__':
    {'partial': lambda: partial(*sys.argv[2:5]), 'cones': lambda: cones(*sys.argv[2:4])}[sys.argv[1]]()
