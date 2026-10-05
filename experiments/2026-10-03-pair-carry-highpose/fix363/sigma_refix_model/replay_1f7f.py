"""Replay align_to_carry@1f7fb800 own frames + own commands through the real v98 provider (HighPoseSource) and
record the own reports the controller would see (inner report at cutoff t; controller time t + 0.16 s) around the
HIGH checkpoint stop (101.9 s). No ground truth is read."""
import sys, json, math, hashlib
sys.path.insert(0, '../ckpt')
import numpy as np
from PIL import Image
import replay
replay.RUNS['ac-1f7f'] = 'v98-dev-probe-align_to_carry-1f7fb800'
_orig = replay.load_case
def load_case(run, rid):
    import json as _j
    from pathlib import Path
    root = replay.OUT/replay.RUNS[run]/'zone_wide_door_geometry_v3'
    rec = _j.load(open(root/'student_record.json'))['robots'][rid]['provider']
    sr = _j.load(open(root/'student_record.json'))
    profiles = sorted((float(e['sim_s']), None if e['profile'] == 'default' else e['profile'])
                      for p in sr.get('pair', []) for e in p.get('robots', {}).get(rid, {}).get('events', [])
                      if e.get('event') == 'motion_profile')
    return dict(root=root, prov=rec['provider'], frames=replay.rjsonl(root/f'robots/{rid}/frames.jsonl'), labels={},
                static=_j.load(open(root/'inputs/static_map.json')), profiles=profiles, rejections=rec.get('frame_rejections', []))
rid = sys.argv[1]
case = load_case('ac-1f7f', rid)
src = replay.build(case)
pf = src.loc._pf
rows = []
for kind, t, payload in replay.events(case):
    if kind == 'report':
        if t >= pf.t-1e-9:
            r = src.report(t)
            if 99. <= t+.16 <= 110.5:
                rows.append({'controller_t': round(t+.16, 4), 't_est': round(float(r.t_est), 4), 'initialized': bool(r.initialized),
                             'last_fix_t': None if r.last_fix_t is None else round(float(r.last_fix_t), 4),
                             'std_xy_m': round(float(r.std_xy_m), 6), 'std_yaw_rad': round(float(r.std_yaw_rad), 6)})
        continue
    if kind == 'profile': src.set_motion_profile(t, payload)
    elif kind == 'cmd': src.on_command(payload)
    elif kind == 'reloc': src.begin_relocalization(t, dict(src.servo))
    else: src.on_frame(t, np.asarray(Image.open(case['root']/payload['path']).convert('RGB')))
rec = case['root']/'student_record.json'
out = {'run': 'outputs/v98-dev-probe-align_to_carry-1f7fb800/zone_wide_door_geometry_v3', 'robot': rid,
       'student_record_sha256': hashlib.sha256(open(rec, 'rb').read()).hexdigest(),
       'replay': 'v98 HighPoseSource, recorded own frames + own commands + recorded begin_relocalization, seed and prior from the record',
       'replayed_counts': dict(src.counts), 'recorded_counts': case['prov']['counts'],
       'replayed_stats': {k: v for k, v in pf.stats.items()}, 'recorded_stats': case['prov']['localizer_stats'], 'rows': rows}
json.dump(out, open(f'replay_1f7f_{rid}.json', 'w'), indent=1, default=str)
print(rid, 'counts', out['replayed_counts'], 'recorded', out['recorded_counts'])
print([ (r['controller_t'], r['last_fix_t'], round(r['std_xy_m']*1e3,1)) for r in rows if 101.3 <= r['controller_t'] <= 102.4])
